from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters.command import CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message

from bot.config import settings
from bot.database import Database
from bot.keyboards import (
    giveaway_entry_keyboard, history_keyboard, quantity_keyboard,
    subscription_keyboard, user_home,
)
from bot.services.giveaways import format_user_status

router = Router(name="user")


async def user_is_subscribed(bot: Bot, channel_id: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(int(channel_id), user_id)
        return member.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        }
    except Exception:
        return False


async def show_giveaway(message_or_callback, giveaway_id: int, db: Database, bot: Bot, user_id: int) -> None:
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway:
        await message_or_callback.answer("Розыгрыш не найден.")
        return
    if giveaway["status"] != "active" or giveaway["closes_at"] <= datetime.now(timezone.utc).isoformat(timespec="seconds"):
        await message_or_callback.answer("Этот розыгрыш уже не принимает участников.")
        return
    if not await user_is_subscribed(bot, giveaway["channel_id"], user_id):
        await message_or_callback.answer(
            "Чтобы участвовать, сначала подпишись на канал розыгрыша, затем нажми «Проверить подписку».",
            reply_markup=subscription_keyboard(giveaway_id, giveaway["channel_url"]),
        )
        return

    usage = await db.get_user_ticket_usage(giveaway_id, user_id)
    purchased, reserved = usage["purchased"], usage["reserved"]
    text = (
        f"🎁 <b>{escape(giveaway['title'])}</b>\n\n"
        f"{escape(giveaway['description'])}\n\n"
        f"🎟 Стоимость билета: <b>{giveaway['ticket_price']} ⭐</b>\n"
        f"🏆 Победителей: <b>{giveaway['winners_count']}</b>\n"
        f"🎫 Оплачено билетов: <b>{purchased} / {giveaway['max_tickets_per_user']}</b>\n"
    )
    if reserved:
        text += f"🕓 Ожидают оплаты: <b>{reserved}</b>\n"
    if purchased or reserved:
        text += "\n✅ <b>Ты уже участвуешь!</b> При желании можешь приобрести дополнительные билеты."
    else:
        text += "\nТы ещё не участвуешь. Приобрети билет, чтобы зарегистрировать участие."
    if not settings.paid_giveaways_enabled:
        text += "\n\n⛔ Приём платных участий временно выключен администратором."
        await message_or_callback.answer(text)
        return
    await message_or_callback.answer(
        text,
        reply_markup=giveaway_entry_keyboard(giveaway_id, purchased, int(giveaway["max_tickets_per_user"]), reserved),
    )


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, db: Database, bot: Bot) -> None:
    user = message.from_user
    await db.upsert_user(user.id, user.username, user.first_name)
    args = command.args or ""
    if args.startswith("join_"):
        try:
            giveaway_id = int(args.removeprefix("join_"))
        except ValueError:
            await message.answer("Некорректная ссылка на розыгрыш.")
            return
        await show_giveaway(message, giveaway_id, db, bot, user.id)
        return

    text = (
        f"👋 Привет, {escape(user.first_name or 'друг')}!\n\n"
        "Здесь ты можешь участвовать в розыгрышах, покупать билеты, "
        "следить за результатами и смотреть историю своих участий.\n\n"
        "Нажми «Мои участия», чтобы открыть историю."
    )
    await message.answer(text, reply_markup=user_home(settings.required_channel_url))


@router.callback_query(F.data == "user:home")
async def home(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "👋 <b>Главное меню</b>\n\nОткрой историю своих участий или вернись к розыгрышу по его ссылке.",
        reply_markup=user_home(settings.required_channel_url),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("user:checksub:"))
async def check_subscription(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    giveaway_id = int(callback.data.rsplit(":", 1)[1])
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway:
        await callback.answer("Розыгрыш не найден", show_alert=True)
        return
    if not await user_is_subscribed(bot, giveaway["channel_id"], callback.from_user.id):
        await callback.answer("Подписка пока не найдена. Подпишись и проверь ещё раз.", show_alert=True)
        return
    await callback.message.answer("✅ Подписка подтверждена.")
    await show_giveaway(callback.message, giveaway_id, db, bot, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("user:join:"))
async def join_callback(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    giveaway_id = int(callback.data.rsplit(":", 1)[1])
    await show_giveaway(callback.message, giveaway_id, db, bot, callback.from_user.id)
    await callback.answer()


async def send_quantity_picker(callback: CallbackQuery, giveaway_id: int, db: Database) -> None:
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway or giveaway["status"] != "active":
        await callback.message.answer("Розыгрыш больше не активен.")
        return
    usage = await db.get_user_ticket_usage(giveaway_id, callback.from_user.id)
    purchased, reserved = usage["purchased"], usage["reserved"]
    remaining = int(giveaway["max_tickets_per_user"]) - purchased - reserved
    if remaining <= 0:
        await callback.message.answer("Ты уже приобрёл максимальное количество билетов.")
        return
    await callback.message.answer(
        f"🎟 Выбери количество дополнительных билетов.\n"
        f"Оплачено: <b>{purchased}</b>, ожидают оплаты: <b>{reserved}</b>.\n"
        f"Всего доступно по лимиту: <b>{remaining}</b>.\n"
        f"Цена одного билета: <b>{giveaway['ticket_price']} ⭐</b>.",
        reply_markup=quantity_keyboard(giveaway_id, remaining),
    )


@router.callback_query(F.data.startswith("user:buy:"))
async def buy_tickets(callback: CallbackQuery, db: Database) -> None:
    giveaway_id = int(callback.data.rsplit(":", 1)[1])
    if not settings.paid_giveaways_enabled:
        await callback.answer("Платная механика временно отключена.", show_alert=True)
        return
    if not await db.has_accepted_terms(callback.from_user.id, settings.terms_version):
        terms_buttons = []
        if settings.terms_url:
            terms_buttons.append([InlineKeyboardButton(text="📄 Полные правила розыгрыша", url=settings.terms_url)])
        if settings.privacy_url:
            terms_buttons.append([InlineKeyboardButton(text="🔒 Политика конфиденциальности", url=settings.privacy_url)])
        terms_buttons.append([InlineKeyboardButton(text="✅ Принимаю правила и политику", callback_data=f"user:terms_accept:{giveaway_id}")])
        markup = InlineKeyboardMarkup(inline_keyboard=terms_buttons)
        await callback.message.answer(
            "Перед покупкой открой полные правила и политику конфиденциальности. "
            "Для продолжения подтверди, что ознакомился с обоими документами и принимаешь правила.",
            reply_markup=markup,
        )
        await callback.answer()
        return
    await send_quantity_picker(callback, giveaway_id, db)
    await callback.answer()


@router.callback_query(F.data.startswith("user:terms_accept:"))
async def accept_terms_callback(callback: CallbackQuery, db: Database) -> None:
    giveaway_id = int(callback.data.rsplit(":", 1)[1])
    await db.accept_terms(callback.from_user.id, settings.terms_version)
    await callback.answer("Согласие сохранено")
    await send_quantity_picker(callback, giveaway_id, db)


@router.callback_query(F.data.startswith("user:qty:"))
async def create_invoice(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    if not settings.paid_giveaways_enabled:
        await callback.answer("Платная механика временно отключена.", show_alert=True)
        return
    if not await db.has_accepted_terms(callback.from_user.id, settings.terms_version):
        await callback.answer("Сначала прими условия через /terms.", show_alert=True)
        return
    _, _, giveaway_id_raw, quantity_raw = callback.data.split(":")
    giveaway_id, quantity = int(giveaway_id_raw), int(quantity_raw)
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway:
        await callback.answer("Розыгрыш не найден.", show_alert=True)
        return
    if not await user_is_subscribed(bot, giveaway["channel_id"], callback.from_user.id):
        await callback.answer("Для покупки нужно быть подписанным на канал.", show_alert=True)
        return
    payload = f"gw:{giveaway_id}:{callback.from_user.id}:{__import__('secrets').token_hex(8)}"
    try:
        order = await db.create_order(
            giveaway_id=giveaway_id,
            user_id=callback.from_user.id,
            quantity=quantity,
            payload=payload,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Билеты: {giveaway['title'][:24]}",
            description=f"{quantity} билет(а/ов) в розыгрыш #{giveaway_id}",
            payload=order["payload"],
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"{quantity} билет(а/ов)", amount=order["amount"])],
        )
    except Exception:
        # Release this reservation if Telegram could not display the invoice.
        await db.expire_order_by_payload(payload)
        await callback.message.answer("Не удалось создать счёт. Попробуй ещё раз чуть позже.")
        raise
    await callback.answer("Счёт отправлен в личные сообщения бота.")


@router.callback_query(F.data.startswith("user:history:"))
async def history(callback: CallbackQuery, db: Database) -> None:
    page = max(0, int(callback.data.rsplit(":", 1)[1]))
    rows = await db.get_user_history(callback.from_user.id, limit=10, offset=page * 10)
    items, has_next = rows[:10], len(rows) > 10
    if not items:
        await callback.message.edit_text("🎟 <b>История участий</b>\n\nПока ты не участвовал ни в одном розыгрыше.", reply_markup=user_home(settings.required_channel_url))
    else:
        lines = ["🎟 <b>История участий</b>"]
        for item in items:
            lines.append(
                f"\n{format_user_status(item['participation_status'])} · <b>{escape(item['title'])}</b>\n"
                f"Билетов: {item['tickets_count']} · Потрачено: {item['total_paid']} ⭐"
            )
        await callback.message.edit_text("\n".join(lines), reply_markup=history_keyboard(items, page, has_next))
    await callback.answer()


@router.callback_query(F.data.startswith("user:history_detail:"))
async def history_detail(callback: CallbackQuery, db: Database) -> None:
    giveaway_id = int(callback.data.rsplit(":", 1)[1])
    detail = await db.get_user_history_detail(giveaway_id, callback.from_user.id)
    if not detail:
        await callback.answer("Участие не найдено", show_alert=True)
        return
    status = format_user_status(detail["participation_status"])
    tickets = ", ".join(f"№{number:05d}" for number in detail["ticket_numbers"]) or "—"
    text = (
        f"🎁 <b>{escape(detail['title'])}</b>\n\n"
        f"Статус: <b>{status}</b>\n"
        f"Куплено билетов: <b>{detail['tickets_count']}</b>\n"
        f"Потрачено: <b>{detail['total_paid']} ⭐</b>\n"
        f"Твои номера: <code>{tickets}</code>\n"
    )
    if detail["participation_status"] == "won":
        text += f"\n🏆 Место: <b>{detail['place']}</b> · Выигрышный билет: <b>№{detail['winning_ticket_number']:05d}</b>"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ К истории", callback_data="user:history:0")]]))
    await callback.answer()


@router.message(F.text == "/terms")
async def terms(message: Message) -> None:
    await message.answer(
        "📄 <b>Условия использования</b>\n\n"
        "Перед запуском платных розыгрышей владелец сервиса обязан опубликовать юридически проверенные правила: "
        "порядок участия, определения победителей, обработки персональных данных, возвратов и разрешения споров.\n\n"
        "Полные правила, контакт поддержки и применимые требования должны быть проверены владельцем сервиса до запуска."
    )
    if settings.terms_url:
        await message.answer(f"Полные правила: {escape(settings.terms_url)}")
    if settings.privacy_url:
        await message.answer(f"Политика конфиденциальности: {escape(settings.privacy_url)}")


@router.message(F.text == "/paysupport")
async def payment_support(message: Message) -> None:
    await message.answer(
        "По вопросам платежей напиши в поддержку: "
        f"<b>{escape(settings.support_contact)}</b>.\n\n"
        "Сохрани чек Telegram и укажи название розыгрыша, дату и сумму платежа."
    )
