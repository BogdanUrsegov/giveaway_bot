from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать розыгрыш", callback_data="admin:create")
    builder.button(text="🎁 Мои розыгрыши", callback_data="admin:list")
    builder.adjust(1)
    return builder.as_markup()


def skip_photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="admin:skip_photo")]])


def publish_keyboard(giveaway_id: int, enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if enabled:
        builder.button(text="📢 Опубликовать в канале", callback_data=f"admin:publish:{giveaway_id}")
    else:
        builder.button(text="⛔ Публикация платного розыгрыша выключена", callback_data="admin:disabled")
    builder.button(text="🎁 Мои розыгрыши", callback_data="admin:list")
    builder.adjust(1)
    return builder.as_markup()


def giveaway_admin_list(items: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        status = {"active": "🟢", "completed": "✅", "draft": "📝", "cancelled": "🚫"}.get(item["status"], "⚪")
        builder.button(text=f"{status} #{item['id']} · {item['title'][:35]}", callback_data=f"admin:detail:{item['id']}")
    builder.button(text="⬅️ В меню", callback_data="admin:menu")
    builder.adjust(1)
    return builder.as_markup()


def admin_detail_keyboard(giveaway_id: int, channel_username: str | None = None, post_message_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Участники", callback_data=f"admin:participants:{giveaway_id}:0")
    if channel_username and post_message_id:
        builder.button(text="🔗 Открыть пост", url=f"https://t.me/{channel_username}/{post_message_id}")
    builder.button(text="⬅️ К розыгрышам", callback_data="admin:list")
    builder.adjust(1)
    return builder.as_markup()


def user_home(required_channel_url: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎟 Мои участия", callback_data="user:history:0")
    if required_channel_url:
        builder.button(text="📢 Подписаться на канал", url=required_channel_url)
    builder.adjust(1)
    return builder.as_markup()


def subscription_keyboard(giveaway_id: int, channel_url: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if channel_url:
        builder.button(text="📢 Подписаться на канал", url=channel_url)
    builder.button(text="✅ Проверить подписку", callback_data=f"user:checksub:{giveaway_id}")
    builder.adjust(1)
    return builder.as_markup()


def giveaway_entry_keyboard(giveaway_id: int, purchased: int, limit: int, reserved: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    remaining = max(0, limit - purchased - reserved)
    if remaining:
        builder.button(text="🎟 Купить билет" if purchased == 0 else "🎟 Купить ещё билеты", callback_data=f"user:buy:{giveaway_id}")
    builder.button(text="🎟 Мои участия", callback_data="user:history:0")
    builder.adjust(1)
    return builder.as_markup()


def quantity_keyboard(giveaway_id: int, remaining: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for quantity in range(1, min(remaining, 10) + 1):
        builder.button(text=f"{quantity} билет{'а' if 2 <= quantity <= 4 else 'ов' if quantity != 1 else ''}", callback_data=f"user:qty:{giveaway_id}:{quantity}")
    builder.button(text="⬅️ Назад", callback_data=f"user:join:{giveaway_id}")
    builder.adjust(2)
    return builder.as_markup()


def history_keyboard(items: list[dict], page: int, has_next: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        status = item["participation_status"]
        icon = {"pending": "⏳", "won": "🏆", "lost": "❌"}.get(status, "•")
        builder.button(text=f"{icon} {item['title'][:35]}", callback_data=f"user:history_detail:{item['id']}")
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"user:history:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"user:history:{page + 1}"))
    if nav:
        builder.row(*nav)
    builder.button(text="🏠 Главное меню", callback_data="user:home")
    builder.adjust(1)
    return builder.as_markup()
