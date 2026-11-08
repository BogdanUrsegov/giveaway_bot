from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.database import Database
from bot.keyboards import (
    admin_detail_keyboard, admin_menu, giveaway_admin_list, publish_keyboard,
    skip_photo_keyboard,
)
from bot.services.giveaways import giveaway_post_text
from bot.states import GiveawayCreate

router = Router(name="admin")
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("🛠 <b>Панель администратора</b>", reply_markup=admin_menu())


@router.message(Command("cancel"))
async def cancel_admin_flow(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("Создание розыгрыша отменено.", reply_markup=admin_menu())


@router.callback_query(F.data == "admin:menu")
async def admin_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("🛠 <b>Панель администратора</b>", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(F.data == "admin:disabled")
async def paid_mode_disabled(callback: CallbackQuery) -> None:
    await callback.answer("Платная механика выключена в настройках проекта.", show_alert=True)


@router.callback_query(F.data == "admin:create")
async def create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await state.set_state(GiveawayCreate.title)
    await callback.message.answer("Введи <b>заголовок</b> розыгрыша (до 100 символов).")
    await callback.answer()


@router.message(GiveawayCreate.title)
async def create_title(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value or len(value) > 100:
        await message.answer("Заголовок должен содержать от 1 до 100 символов. Попробуй ещё раз.")
        return
    await state.update_data(title=value)
    await state.set_state(GiveawayCreate.description)
    await message.answer("Введи <b>описание и условия</b> розыгрыша (до 500 символов).")


@router.message(GiveawayCreate.description)
async def create_description(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value or len(value) > 500:
        await message.answer("Описание должно содержать от 1 до 500 символов. Попробуй ещё раз.")
        return
    await state.update_data(description=value)
    await state.set_state(GiveawayCreate.ticket_price)
    await message.answer("Введи <b>стоимость одного билета в Telegram Stars</b> (целое число, например 25).")


@router.message(GiveawayCreate.ticket_price)
async def create_ticket_price(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
        if not 1 <= value <= 100000:
            raise ValueError
    except ValueError:
        await message.answer("Введи целое число от 1 до 100000 Stars.")
        return
    await state.update_data(ticket_price=value)
    await state.set_state(GiveawayCreate.winners_count)
    await message.answer("Сколько будет <b>победителей</b>? Введи целое число от 1 до 100.")


@router.message(GiveawayCreate.winners_count)
async def create_winners(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
        if not 1 <= value <= 100:
            raise ValueError
    except ValueError:
        await message.answer("Введи целое число от 1 до 100.")
        return
    await state.update_data(winners_count=value)
    await state.set_state(GiveawayCreate.max_tickets_per_user)
    await message.answer("Введи <b>максимальное количество билетов на одного пользователя</b> за весь розыгрыш (от 1 до 1000).")


@router.message(GiveawayCreate.max_tickets_per_user)
async def create_max_tickets(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
        if not 1 <= value <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Введи целое число от 1 до 1000.")
        return
    await state.update_data(max_tickets_per_user=value)
    await state.set_state(GiveawayCreate.closes_at)
    await message.answer(
        "Введи дату и время завершения в формате <code>ГГГГ-ММ-ДД ЧЧ:ММ</code>.\n"
        f"Часовой пояс: <b>{escape(settings.timezone)}</b>. Например: <code>2026-12-31 20:00</code>."
    )


@router.message(GiveawayCreate.closes_at)
async def create_closing_date(message: Message, state: FSMContext) -> None:
    from bot.services.giveaways import parse_closing_datetime
    try:
        closes_at = parse_closing_datetime(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(closes_at=closes_at)
    await state.set_state(GiveawayCreate.photo)
    await message.answer(
        "Пришли <b>одно фото</b> для публикации или пропусти этот шаг.",
        reply_markup=skip_photo_keyboard(),
    )


@router.callback_query(GiveawayCreate.photo, F.data == "admin:skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(photo_file_id=None)
    await state.set_state(GiveawayCreate.channel)
    await callback.message.answer("Введи публичный канал для публикации в формате <code>@channel</code>. Бот должен быть администратором с правом публикации сообщений.")
    await callback.answer()


@router.message(GiveawayCreate.photo, F.photo)
async def receive_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await state.set_state(GiveawayCreate.channel)
    await message.answer("Фото сохранено. Теперь введи публичный канал для публикации в формате <code>@channel</code>. Бот должен быть администратором с правом публикации сообщений.")


@router.message(GiveawayCreate.photo)
async def invalid_photo(message: Message) -> None:
    if (message.text or "").strip().lower() in {"пропустить", "skip"}:
        await message.bot.send_message(message.chat.id, "Фото пропущено. Введи публичный канал в формате <code>@channel</code>.")
        return
    await message.answer("Пришли одно фото или нажми кнопку «Пропустить».", reply_markup=skip_photo_keyboard())


@router.message(GiveawayCreate.channel)
async def create_channel(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    channel_input = (message.text or "").strip()
    if not channel_input.startswith("@"):
        await message.answer("Пока поддерживаются публичные каналы. Введи username канала в формате <code>@channel</code>.")
        return
    try:
        chat = await bot.get_chat(channel_input)
        if chat.type != ChatType.CHANNEL or not chat.username:
            raise ValueError("Укажи публичный Telegram-канал.")
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            raise ValueError("Сначала добавь бота администратором канала.")
        if member.status == ChatMemberStatus.ADMINISTRATOR and not getattr(member, "can_post_messages", False):
            raise ValueError("У бота нет права публиковать сообщения в канале.")
    except Exception as exc:
        await message.answer(f"Не удалось проверить канал: {escape(str(exc))}\nПроверь username и права бота.")
        return

    data = await state.get_data()
    giveaway_id = await db.create_giveaway(
        admin_id=message.from_user.id,
        title=data["title"],
        description=data["description"],
        ticket_price=data["ticket_price"],
        winners_count=data["winners_count"],
        max_tickets_per_user=data["max_tickets_per_user"],
        closes_at=data["closes_at"],
        timezone_name=settings.timezone,
        photo_file_id=data.get("photo_file_id"),
        channel_id=str(chat.id),
        channel_username=chat.username,
        channel_url=f"https://t.me/{chat.username}",
    )
    await state.clear()
    giveaway = await db.get_giveaway(giveaway_id)
    me = await bot.get_me()
    preview = giveaway_post_text(giveaway, me.username or "")
    await message.answer(
        f"<b>Предпросмотр розыгрыша #{giveaway_id}</b>\n\n{preview}\n\n"
        f"Максимум билетов на человека: <b>{data['max_tickets_per_user']}</b>.\n"
        "Проверь текст. После публикации изменить условия нельзя.",
        reply_markup=publish_keyboard(giveaway_id, settings.paid_giveaways_enabled),
    )
    if data.get("photo_file_id"):
        await message.answer_photo(data["photo_file_id"], caption="Фото, которое будет использовано в посте.")


@router.callback_query(F.data.startswith("admin:publish:"))
async def publish_giveaway(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not settings.paid_giveaways_enabled:
        await callback.answer("Платные розыгрыши отключены до проверки правовой допустимости.", show_alert=True)
        return
    giveaway_id = int(callback.data.rsplit(":", 1)[1])
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway or giveaway["admin_id"] != callback.from_user.id or giveaway["status"] != "draft":
        await callback.answer("Черновик не найден или уже опубликован.", show_alert=True)
        return
    me = await bot.get_me()
    post_text = giveaway_post_text(giveaway, me.username or "")
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    join_url = f"https://t.me/{me.username}?start=join_{giveaway_id}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟 Участвовать", url=join_url)]])
    try:
        if giveaway["photo_file_id"]:
            post = await bot.send_photo(
                chat_id=int(giveaway["channel_id"]), photo=giveaway["photo_file_id"],
                caption=post_text, parse_mode=ParseMode.HTML, reply_markup=markup,
            )
        else:
            post = await bot.send_message(
                chat_id=int(giveaway["channel_id"]), text=post_text,
                parse_mode=ParseMode.HTML, reply_markup=markup,
            )
        await db.activate_giveaway(giveaway_id, post.message_id)
        post_link = f"https://t.me/{giveaway['channel_username']}/{post.message_id}"
        await callback.message.answer(f"✅ Розыгрыш #{giveaway_id} опубликован.\n{post_link}")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Опубликовано")
    except Exception as exc:
        logger.exception("Could not publish giveaway %s", giveaway_id)
        await callback.answer("Не удалось опубликовать. Проверь права бота в канале.", show_alert=True)
        await callback.message.answer(f"Ошибка публикации: <code>{escape(str(exc))[:500]}</code>")


@router.callback_query(F.data == "admin:list")
async def admin_list(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    items = await db.list_giveaways(callback.from_user.id)
    if not items:
        await callback.message.edit_text("Пока нет розыгрышей.", reply_markup=admin_menu())
    else:
        await callback.message.edit_text("🎁 <b>Твои розыгрыши</b>", reply_markup=giveaway_admin_list(items))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:detail:"))
async def admin_detail(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    giveaway_id = int(callback.data.rsplit(":", 1)[1])
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway or giveaway["admin_id"] != callback.from_user.id:
        await callback.answer("Розыгрыш не найден", show_alert=True)
        return
    stats = await db.get_giveaway_stats(giveaway_id)
    end = datetime.fromisoformat(giveaway["closes_at"]).astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    text = (
        f"🎁 <b>{escape(giveaway['title'])}</b> · #{giveaway_id}\n"
        f"Статус: <b>{giveaway['status']}</b>\n\n"
        f"👥 Уникальных участников: <b>{stats['participants']}</b>\n"
        f"🎟 Продано билетов: <b>{stats['tickets']}</b>\n"
        f"⭐ Получено Stars: <b>{stats['revenue']}</b>\n"
        f"💳 Цена билета: <b>{giveaway['ticket_price']} ⭐</b>\n"
        f"🏆 Победителей: <b>{giveaway['winners_count']}</b>\n"
        f"Лимит билетов на человека: <b>{giveaway['max_tickets_per_user']}</b>\n"
        f"Завершение: <b>{end}</b>\n"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_detail_keyboard(giveaway_id, giveaway["channel_username"], giveaway["post_message_id"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:participants:"))
async def admin_participants(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, _, giveaway_id_raw, offset_raw = callback.data.split(":")
    giveaway_id, offset = int(giveaway_id_raw), int(offset_raw)
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway or giveaway["admin_id"] != callback.from_user.id:
        await callback.answer("Розыгрыш не найден", show_alert=True)
        return
    users = await db.list_participants(giveaway_id, limit=20, offset=offset)
    lines = [f"👥 <b>Участники #{giveaway_id}</b>"]
    if not users:
        lines.append("Пока участников нет.")
    for item in users:
        name = f"@{item['username']}" if item["username"] else escape(item["first_name"] or str(item["user_id"]))
        lines.append(f"• {name} — <b>{item['tickets_count']}</b> бил., {item['total_paid']} ⭐")
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    if offset > 0:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin:participants:{giveaway_id}:{max(0, offset-20)}"))
    if len(users) == 20:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin:participants:{giveaway_id}:{offset+20}"))
    buttons.append(InlineKeyboardButton(text="⬅️ К статистике", callback_data=f"admin:detail:{giveaway_id}"))
    markup = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await callback.message.edit_text("\n".join(lines), reply_markup=markup)
    await callback.answer()
