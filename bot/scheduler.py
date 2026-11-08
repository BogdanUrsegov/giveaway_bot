from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot

from bot.database import Database

logger = logging.getLogger(__name__)


async def process_due_giveaways(bot: Bot, db: Database) -> None:
    await db.expire_orders()
    for giveaway in await db.due_giveaways():
        result = await db.finish_giveaway(int(giveaway["id"]))
        if result is None:
            continue
        winners = result["winners"]
        if winners:
            winner_lines = []
            for place, winner in enumerate(winners, start=1):
                name = f"@{winner['username']}" if winner["username"] else html.escape(winner["first_name"] or str(winner["user_id"]))
                winner_lines.append(
                    f"{place}. {name} — билет №{int(winner['ticket_number']):05d}"
                )
            result_text = (
                f"🏆 <b>Итоги розыгрыша: {html.escape(giveaway['title'])}</b>\n\n"
                + "\n".join(winner_lines)
            )
        else:
            result_text = (
                f"ℹ️ <b>Розыгрыш «{html.escape(giveaway['title'])}» завершён.</b>\n\n"
                "Билетов не было приобретено, победители не определены."
            )
        try:
            posted = await bot.send_message(int(giveaway["channel_id"]), result_text)
            await db.set_results_message(int(giveaway["id"]), posted.message_id)
        except Exception:
            logger.exception("Could not publish results for giveaway %s", giveaway["id"])

        winner_ids = {int(item["user_id"]) for item in winners}
        for user_id in await db.get_participant_ids(int(giveaway["id"])):
            try:
                if user_id in winner_ids:
                    winner = next(item for item in winners if int(item["user_id"]) == user_id)
                    await bot.send_message(
                        user_id,
                        f"🏆 <b>Поздравляем! Ты победил в розыгрыше «{html.escape(giveaway['title'])}»!</b>\n"
                        f"Твоё место: <b>{next(i for i,item in enumerate(winners,1) if int(item['user_id']) == user_id)}</b>.\n"
                        f"Выигрышный билет: <b>№{int(winner['ticket_number']):05d}</b>.",
                    )
                else:
                    await bot.send_message(
                        user_id,
                        f"Розыгрыш «{html.escape(giveaway['title'])}» завершён. В этот раз ты не выиграл.\n"
                        "Спасибо за участие! Посмотреть историю можно через /start.",
                    )
            except Exception:
                logger.info("Could not notify participant %s about giveaway %s", user_id, giveaway["id"])


async def scheduler_loop(bot: Bot, db: Database) -> None:
    while True:
        try:
            await process_due_giveaways(bot, db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Giveaway scheduler iteration failed")
        await asyncio.sleep(15)
