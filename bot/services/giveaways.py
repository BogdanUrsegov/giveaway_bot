from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

from bot.config import settings


def parse_closing_datetime(value: str) -> str:
    """Parse admin input in configured local timezone and return UTC ISO string."""
    try:
        local_value = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValueError(f"Введи дату в формате ГГГГ-ММ-ДД ЧЧ:ММ ({settings.timezone}).") from exc
    aware = local_value.replace(tzinfo=ZoneInfo(settings.timezone))
    if aware <= datetime.now(aware.tzinfo):
        raise ValueError("Дата завершения должна быть в будущем.")
    return aware.astimezone(timezone.utc).isoformat(timespec="seconds")


def giveaway_post_text(giveaway: dict, bot_username: str) -> str:
    title = escape(giveaway["title"])
    description = escape(giveaway["description"])
    closes_local = datetime.fromisoformat(giveaway["closes_at"]).astimezone(ZoneInfo(giveaway["timezone"]))
    closes_text = closes_local.strftime("%d.%m.%Y в %H:%M")
    return (
        f"🎁 <b>{title}</b>\n\n"
        f"{description}\n\n"
        f"🎟 Стоимость билета: <b>{giveaway['ticket_price']} ⭐</b>\n"
        f"🏆 Победителей: <b>{giveaway['winners_count']}</b>\n"
        f"👤 Максимум билетов на человека: <b>{giveaway['max_tickets_per_user']}</b>\n"
        f"⏳ Окончание: <b>{closes_text} ({escape(giveaway['timezone'])})</b>\n\n"
        "Нажми кнопку ниже, чтобы посмотреть условия и приобрести билет."
    )


def format_user_status(status: str) -> str:
    return {"pending": "⏳ В ожидании", "won": "🏆 Победил", "lost": "❌ Не выиграл"}.get(status, status)


def join_deep_link(bot_username: str, giveaway_id: int) -> str:
    return f"https://t.me/{bot_username}?start=join_{giveaway_id}"
