from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.database import Database
from bot.database.db import iso_utc


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.temp.name) / "test.db"))
        await self.db.init()
        await self.db.upsert_user(1001, "alice", "Alice")

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def create_active_giveaway(self, max_tickets: int = 3) -> int:
        gid = await self.db.create_giveaway(
            admin_id=1001,
            title="Test giveaway",
            description="Description",
            ticket_price=10,
            winners_count=1,
            max_tickets_per_user=max_tickets,
            closes_at=iso_utc(datetime.now(timezone.utc) + timedelta(days=1)),
            timezone_name="UTC",
            photo_file_id=None,
            channel_id="-100123",
            channel_username="test_channel",
            channel_url="https://t.me/test_channel",
        )
        await self.db.activate_giveaway(gid, 50)
        return gid

    async def test_ticket_limit_includes_unpaid_reservations(self) -> None:
        gid = await self.create_active_giveaway(max_tickets=3)
        first = await self.db.create_order(
            giveaway_id=gid, user_id=1001, quantity=2, payload="first-order"
        )
        self.assertEqual(first["amount"], 20)
        usage = await self.db.get_user_ticket_usage(gid, 1001)
        self.assertEqual(usage, {"purchased": 0, "reserved": 2})
        with self.assertRaises(ValueError):
            await self.db.create_order(
                giveaway_id=gid, user_id=1001, quantity=2, payload="second-order"
            )


    async def test_precheckout_is_idempotent_but_amount_is_validated(self) -> None:
        gid = await self.create_active_giveaway(max_tickets=3)
        order = await self.db.create_order(
            giveaway_id=gid, user_id=1001, quantity=1, payload="retryable-order"
        )
        self.assertFalse(await self.db.accept_order(
            payload=order["payload"], user_id=1001, amount=999, currency="XTR"
        ))
        self.assertTrue(await self.db.accept_order(
            payload=order["payload"], user_id=1001, amount=10, currency="XTR"
        ))
        self.assertTrue(await self.db.accept_order(
            payload=order["payload"], user_id=1001, amount=10, currency="XTR"
        ))

    async def test_successful_payment_creates_distinct_tickets_once(self) -> None:
        gid = await self.create_active_giveaway(max_tickets=3)
        order = await self.db.create_order(
            giveaway_id=gid, user_id=1001, quantity=2, payload="payment-payload"
        )
        accepted = await self.db.accept_order(
            payload=order["payload"], user_id=1001, amount=20, currency="XTR"
        )
        self.assertTrue(accepted)
        result = await self.db.complete_payment(
            payload=order["payload"], user_id=1001, amount=20,
            currency="XTR", telegram_charge_id="charge-1",
        )
        self.assertEqual(result["status"], "paid")
        self.assertEqual(result["ticket_numbers"], [1, 2])
        duplicate = await self.db.complete_payment(
            payload=order["payload"], user_id=1001, amount=20,
            currency="XTR", telegram_charge_id="charge-1",
        )
        self.assertEqual(duplicate["status"], "duplicate")
        participant = await self.db.get_user_participation(gid, 1001)
        self.assertEqual(participant["tickets_count"], 2)
        self.assertEqual(participant["total_paid"], 20)
        usage = await self.db.get_user_ticket_usage(gid, 1001)
        self.assertEqual(usage, {"purchased": 2, "reserved": 0})


if __name__ == "__main__":
    unittest.main()
