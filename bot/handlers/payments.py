from __future__ import annotations

import logging

from aiogram import F, Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import Message, PreCheckoutQuery

from bot.config import settings
from bot.database import Database

router = Router(name="payments")
logger = logging.getLogger(__name__)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, db: Database, bot: Bot) -> None:
    if not settings.paid_giveaways_enabled:
        await query.answer(ok=False, error_message="Платные розыгрыши временно отключены.")
        return
    try:
        order_context = await db.get_order_giveaway_context(
            payload=query.invoice_payload, user_id=query.from_user.id
        )
        if not order_context:
            accepted = False
        elif (order_context["status"] not in {"pending", "accepted"}
              or order_context["giveaway_status"] != "active"):
            accepted = False
        else:
            try:
                member = await bot.get_chat_member(
                    int(order_context["channel_id"]), query.from_user.id
                )
                subscribed = member.status in {
                    ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR
                }
            except Exception:
                subscribed = False
            if not subscribed:
                await db.expire_order_by_payload(query.invoice_payload)
                accepted = False
            else:
                accepted = await db.accept_order(
                    payload=query.invoice_payload,
                    user_id=query.from_user.id,
                    amount=query.total_amount,
                    currency=query.currency,
                )
    except Exception:
        logger.exception("Pre-checkout validation failed for user %s", query.from_user.id)
        accepted = False
    if not accepted:
        await query.answer(
            ok=False,
            error_message="Счёт устарел или лимит билетов уже исчерпан. Вернись в розыгрыш и создай новый счёт.",
        )
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, db: Database, bot: Bot) -> None:
    payment = message.successful_payment
    try:
        result = await db.complete_payment(
            payload=payment.invoice_payload,
            user_id=message.from_user.id,
            amount=payment.total_amount,
            currency=payment.currency,
            telegram_charge_id=payment.telegram_payment_charge_id,
            provider_charge_id=payment.provider_payment_charge_id,
        )
    except Exception:
        logger.exception("Failed to store successful Stars payment from user %s", message.from_user.id)
        # A charge must never be silently kept without delivering tickets.
        try:
            await bot.refund_star_payment(
                user_id=message.from_user.id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
            await message.answer("Не удалось зарегистрировать покупку. Telegram Stars возвращены.")
        except Exception:
            logger.exception("Automatic refund failed for charge %s", payment.telegram_payment_charge_id)
            await message.answer("Платёж получен, но покупку не удалось завершить. Напиши в /paysupport.")
        return

    if result["status"] == "duplicate":
        return
    if result["status"] != "paid":
        try:
            await bot.refund_star_payment(
                user_id=message.from_user.id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
            )
            await message.answer("Розыгрыш уже завершён или счёт устарел. Оплата возвращена.")
        except Exception:
            logger.exception("Refund failed for late payment %s", payment.telegram_payment_charge_id)
            await message.answer("Не удалось автоматически вернуть оплату. Напиши в /paysupport.")
        return

    numbers = ", ".join(f"№{number:05d}" for number in result["ticket_numbers"])
    await message.answer(
        "✅ <b>Оплата прошла успешно!</b>\n\n"
        f"Розыгрыш: <b>{result['title']}</b>\n"
        f"Куплено билетов: <b>{result['quantity']}</b>\n"
        f"Списано: <b>{result['amount']} ⭐</b>\n"
        f"Твои номера: <code>{numbers}</code>\n\n"
        "Ты участвуешь. Посмотреть статус можно в разделе «Мои участия» через /start."
    )
