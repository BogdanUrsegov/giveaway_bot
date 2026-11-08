from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot.config import settings
from bot.database import Database
from bot.handlers import admin_router, payments_router, user_router
from bot.scheduler import scheduler_loop

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    db = Database(settings.db_path)
    await db.init()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage(), db=db)
    dp.include_router(admin_router)
    dp.include_router(payments_router)
    dp.include_router(user_router)

    @dp.errors()
    async def handle_update_error(event: ErrorEvent) -> bool:
        logger.exception("Unhandled update error", exc_info=event.exception)
        return True

    scheduler_task: asyncio.Task | None = None
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        me = await bot.get_me()
        logger.info("Starting @%s; paid mode=%s", me.username, settings.paid_giveaways_enabled)
        if not settings.paid_giveaways_enabled:
            logger.warning(
                "Paid giveaways are disabled. Set PAID_GIVEAWAYS_ENABLED=true only after platform/legal review."
            )
        scheduler_task = asyncio.create_task(scheduler_loop(bot, db), name="giveaway-scheduler")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if scheduler_task:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown requested")
