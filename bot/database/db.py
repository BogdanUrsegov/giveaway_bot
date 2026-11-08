"""SQLite persistence layer. All money values are integer Telegram Stars."""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    current = value or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        db = await aiosqlite.connect(self.path, timeout=10)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 10000")
        try:
            yield db
        finally:
            await db.close()

    async def init(self) -> None:
        async with self.connection() as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    ticket_price INTEGER NOT NULL CHECK(ticket_price > 0),
                    winners_count INTEGER NOT NULL CHECK(winners_count > 0),
                    max_tickets_per_user INTEGER NOT NULL CHECK(max_tickets_per_user > 0),
                    closes_at TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    photo_file_id TEXT,
                    channel_id TEXT NOT NULL,
                    channel_username TEXT,
                    channel_url TEXT,
                    post_message_id INTEGER,
                    results_message_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK(status IN ('draft','active','finishing','completed','cancelled')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS participants (
                    giveaway_id INTEGER NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    tickets_count INTEGER NOT NULL DEFAULT 0 CHECK(tickets_count >= 0),
                    total_paid INTEGER NOT NULL DEFAULT 0 CHECK(total_paid >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (giveaway_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL UNIQUE,
                    giveaway_id INTEGER NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    amount INTEGER NOT NULL CHECK(amount > 0),
                    currency TEXT NOT NULL DEFAULT 'XTR',
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','accepted','paid','expired','refunded')),
                    expires_at TEXT NOT NULL,
                    telegram_charge_id TEXT UNIQUE,
                    provider_charge_id TEXT,
                    created_at TEXT NOT NULL,
                    paid_at TEXT
                );

                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    giveaway_id INTEGER NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    ticket_number INTEGER NOT NULL,
                    order_id TEXT NOT NULL REFERENCES orders(id),
                    created_at TEXT NOT NULL,
                    UNIQUE(giveaway_id, ticket_number)
                );

                CREATE TABLE IF NOT EXISTS winners (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    giveaway_id INTEGER NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
                    place INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(giveaway_id, user_id),
                    UNIQUE(giveaway_id, ticket_id),
                    UNIQUE(giveaway_id, place)
                );

                CREATE TABLE IF NOT EXISTS terms_acceptances (
                    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    accepted_at TEXT NOT NULL,
                    terms_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS payment_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_charge_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_giveaways_admin_status ON giveaways(admin_id, status, id DESC);
                CREATE INDEX IF NOT EXISTS idx_giveaways_due ON giveaways(status, closes_at);
                CREATE INDEX IF NOT EXISTS idx_orders_giveaway_user_status ON orders(giveaway_id, user_id, status, expires_at);
                CREATE INDEX IF NOT EXISTS idx_tickets_giveaway ON tickets(giveaway_id, id);
                CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id, giveaway_id);
                CREATE INDEX IF NOT EXISTS idx_winners_user ON winners(user_id, giveaway_id);
                """
            )
            await db.commit()

    async def upsert_user(self, user_id: int, username: str | None, first_name: str) -> None:
        async with self.connection() as db:
            await db.execute(
                """INSERT INTO users(user_id, username, first_name, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
                     first_name=excluded.first_name""",
                (user_id, username, first_name or "", iso_utc()),
            )
            await db.commit()

    async def has_accepted_terms(self, user_id: int, terms_version: str) -> bool:
        async with self.connection() as db:
            cursor = await db.execute(
                "SELECT 1 FROM terms_acceptances WHERE user_id=? AND terms_version=?",
                (user_id, terms_version),
            )
            return await cursor.fetchone() is not None

    async def accept_terms(self, user_id: int, terms_version: str) -> None:
        async with self.connection() as db:
            await db.execute(
                "INSERT INTO terms_acceptances(user_id,accepted_at,terms_version) VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET accepted_at=excluded.accepted_at,terms_version=excluded.terms_version",
                (user_id, iso_utc(), terms_version),
            )
            await db.commit()

    async def create_giveaway(self, *, admin_id: int, title: str, description: str,
                              ticket_price: int, winners_count: int, max_tickets_per_user: int,
                              closes_at: str, timezone_name: str, photo_file_id: str | None,
                              channel_id: str, channel_username: str | None,
                              channel_url: str | None) -> int:
        now = iso_utc()
        async with self.connection() as db:
            cursor = await db.execute(
                """INSERT INTO giveaways(
                    admin_id,title,description,ticket_price,winners_count,max_tickets_per_user,
                    closes_at,timezone,photo_file_id,channel_id,channel_username,channel_url,
                    status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'draft',?,?)""",
                (admin_id, title, description, ticket_price, winners_count,
                 max_tickets_per_user, closes_at, timezone_name, photo_file_id,
                 channel_id, channel_username, channel_url, now, now),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_giveaway(self, giveaway_id: int) -> dict[str, Any] | None:
        async with self.connection() as db:
            cursor = await db.execute("SELECT * FROM giveaways WHERE id=?", (giveaway_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def activate_giveaway(self, giveaway_id: int, post_message_id: int) -> None:
        async with self.connection() as db:
            await db.execute(
                "UPDATE giveaways SET status='active', post_message_id=?, updated_at=? WHERE id=? AND status='draft'",
                (post_message_id, iso_utc(), giveaway_id),
            )
            await db.commit()

    async def list_giveaways(self, admin_id: int, limit: int = 30) -> list[dict[str, Any]]:
        async with self.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM giveaways WHERE admin_id=? ORDER BY id DESC LIMIT ?",
                (admin_id, limit),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def get_giveaway_stats(self, giveaway_id: int) -> dict[str, int]:
        async with self.connection() as db:
            cursor = await db.execute(
                """SELECT COUNT(*) AS participants,
                          COALESCE(SUM(tickets_count),0) AS tickets,
                          COALESCE(SUM(total_paid),0) AS revenue
                   FROM participants WHERE giveaway_id=?""",
                (giveaway_id,),
            )
            row = await cursor.fetchone()
            return {key: int(row[key]) for key in ("participants", "tickets", "revenue")}

    async def list_participants(self, giveaway_id: int, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        async with self.connection() as db:
            cursor = await db.execute(
                """SELECT p.user_id,p.tickets_count,p.total_paid,u.username,u.first_name
                   FROM participants p JOIN users u ON u.user_id=p.user_id
                   WHERE p.giveaway_id=? ORDER BY p.tickets_count DESC,p.created_at ASC
                   LIMIT ? OFFSET ?""",
                (giveaway_id, limit, offset),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def get_participant_tickets(self, giveaway_id: int, user_id: int) -> list[int]:
        async with self.connection() as db:
            cursor = await db.execute(
                "SELECT ticket_number FROM tickets WHERE giveaway_id=? AND user_id=? ORDER BY ticket_number",
                (giveaway_id, user_id),
            )
            return [int(row[0]) for row in await cursor.fetchall()]

    async def get_user_participation(self, giveaway_id: int, user_id: int) -> dict[str, Any] | None:
        async with self.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM participants WHERE giveaway_id=? AND user_id=?",
                (giveaway_id, user_id),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_ticket_usage(self, giveaway_id: int, user_id: int) -> dict[str, int]:
        now = iso_utc()
        async with self.connection() as db:
            cursor = await db.execute(
                "SELECT COALESCE(tickets_count,0) AS purchased FROM participants WHERE giveaway_id=? AND user_id=?",
                (giveaway_id, user_id),
            )
            participant = await cursor.fetchone()
            purchased = int(participant["purchased"]) if participant else 0
            cursor = await db.execute(
                """SELECT COALESCE(SUM(quantity),0) AS reserved FROM orders
                   WHERE giveaway_id=? AND user_id=? AND status IN ('pending','accepted') AND expires_at>?""",
                (giveaway_id, user_id, now),
            )
            reserved = int((await cursor.fetchone())["reserved"])
            return {"purchased": purchased, "reserved": reserved}

    async def get_user_history(self, user_id: int, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        async with self.connection() as db:
            cursor = await db.execute(
                """SELECT g.id,g.title,g.status,g.closes_at,g.ticket_price,
                          p.tickets_count,p.total_paid,
                          CASE WHEN w.user_id IS NOT NULL THEN 'won'
                               WHEN g.status='completed' THEN 'lost'
                               ELSE 'pending' END AS participation_status
                   FROM participants p
                   JOIN giveaways g ON g.id=p.giveaway_id
                   LEFT JOIN winners w ON w.giveaway_id=g.id AND w.user_id=p.user_id
                   WHERE p.user_id=? ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
                (user_id, limit + 1, offset),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def get_user_history_detail(self, giveaway_id: int, user_id: int) -> dict[str, Any] | None:
        async with self.connection() as db:
            cursor = await db.execute(
                """SELECT g.*,p.tickets_count,p.total_paid,w.place,w.ticket_id,
                          t.ticket_number AS winning_ticket_number,
                          CASE WHEN w.user_id IS NOT NULL THEN 'won'
                               WHEN g.status='completed' THEN 'lost'
                               ELSE 'pending' END AS participation_status
                   FROM giveaways g JOIN participants p ON p.giveaway_id=g.id
                   LEFT JOIN winners w ON w.giveaway_id=g.id AND w.user_id=p.user_id
                   LEFT JOIN tickets t ON t.id=w.ticket_id
                   WHERE g.id=? AND p.user_id=?""",
                (giveaway_id, user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            result = dict(row)
            tickets_cursor = await db.execute(
                "SELECT ticket_number FROM tickets WHERE giveaway_id=? AND user_id=? ORDER BY ticket_number",
                (giveaway_id, user_id),
            )
            result["ticket_numbers"] = [int(item[0]) for item in await tickets_cursor.fetchall()]
            return result

    async def create_order(self, *, giveaway_id: int, user_id: int, quantity: int,
                           payload: str, ttl_seconds: int = 1800) -> dict[str, Any]:
        now = utc_now()
        expires = iso_utc(now.replace(microsecond=0) + timedelta(seconds=ttl_seconds))
        async with self.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute("SELECT * FROM giveaways WHERE id=?", (giveaway_id,))
            giveaway = await cursor.fetchone()
            if not giveaway or giveaway["status"] != "active":
                raise ValueError("Розыгрыш уже не принимает участников.")
            if giveaway["closes_at"] <= iso_utc(now):
                raise ValueError("Время участия в розыгрыше закончилось.")
            cursor = await db.execute(
                "SELECT COALESCE(tickets_count,0) AS n FROM participants WHERE giveaway_id=? AND user_id=?",
                (giveaway_id, user_id),
            )
            participant = await cursor.fetchone()
            purchased = int(participant["n"]) if participant else 0
            cursor = await db.execute(
                """SELECT COALESCE(SUM(quantity),0) AS n FROM orders
                   WHERE giveaway_id=? AND user_id=? AND status IN ('pending','accepted') AND expires_at>?""",
                (giveaway_id, user_id, iso_utc(now)),
            )
            reserved = int((await cursor.fetchone())["n"])
            if purchased + reserved + quantity > int(giveaway["max_tickets_per_user"]):
                raise ValueError(f"Можно приобрести не больше {giveaway['max_tickets_per_user']} билетов за весь розыгрыш.")
            if quantity < 1 or quantity > 10:
                raise ValueError("Некорректное количество билетов.")
            order_id = secrets.token_hex(12)
            amount = int(giveaway["ticket_price"]) * quantity
            await db.execute(
                """INSERT INTO orders(id,payload,giveaway_id,user_id,quantity,amount,currency,status,expires_at,created_at)
                   VALUES(?,?,?,?,?,?,'XTR','pending',?,?)""",
                (order_id, payload, giveaway_id, user_id, quantity, amount, expires, iso_utc(now)),
            )
            await db.commit()
            return {"id": order_id, "payload": payload, "giveaway_id": giveaway_id,
                    "user_id": user_id, "quantity": quantity, "amount": amount,
                    "expires_at": expires, "giveaway": dict(giveaway)}

    async def get_order_giveaway_context(self, *, payload: str, user_id: int) -> dict[str, Any] | None:
        """Return the channel and giveaway state for a pending invoice checkout."""
        async with self.connection() as db:
            cursor = await db.execute(
                """SELECT o.id,o.status,o.expires_at,o.amount,o.currency,
                          g.id AS giveaway_id,g.status AS giveaway_status,
                          g.closes_at,g.channel_id
                   FROM orders o JOIN giveaways g ON g.id=o.giveaway_id
                   WHERE o.payload=? AND o.user_id=?""",
                (payload, user_id),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def accept_order(self, *, payload: str, user_id: int, amount: int, currency: str) -> bool:
        now = iso_utc()
        async with self.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT o.*,g.status AS giveaway_status,g.closes_at,g.max_tickets_per_user FROM orders o "
                "JOIN giveaways g ON g.id=o.giveaway_id WHERE o.payload=? AND o.user_id=?",
                (payload, user_id),
            )
            order = await cursor.fetchone()
            if not order or order["status"] not in {"pending", "accepted"} or order["expires_at"] <= now:
                await db.rollback()
                return False
            if order["giveaway_status"] != "active" or order["closes_at"] <= now:
                await db.rollback()
                return False
            if currency != "XTR" or amount != int(order["amount"]):
                await db.rollback()
                return False
            if order["status"] == "pending":
                await db.execute("UPDATE orders SET status='accepted' WHERE id=?", (order["id"],))
            await db.commit()
            return True

    async def complete_payment(self, *, payload: str, user_id: int, amount: int,
                               currency: str, telegram_charge_id: str,
                               provider_charge_id: str | None = None) -> dict[str, Any]:
        now = iso_utc()
        async with self.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT id FROM payment_events WHERE telegram_charge_id=?", (telegram_charge_id,)
            )
            if await cursor.fetchone():
                await db.rollback()
                return {"status": "duplicate"}
            cursor = await db.execute("SELECT * FROM orders WHERE payload=? AND user_id=?", (payload, user_id))
            order = await cursor.fetchone()
            if (not order or order["status"] != "accepted" or order["expires_at"] <= now
                    or order["amount"] != amount or currency != "XTR"):
                await db.rollback()
                return {"status": "late_or_invalid"}
            cursor = await db.execute("SELECT * FROM giveaways WHERE id=?", (order["giveaway_id"],))
            giveaway = await cursor.fetchone()
            if not giveaway or giveaway["status"] != "active" or giveaway["closes_at"] <= now:
                await db.rollback()
                return {"status": "late_or_invalid"}

            cursor = await db.execute(
                "SELECT COALESCE(tickets_count,0) AS purchased FROM participants WHERE giveaway_id=? AND user_id=?",
                (order["giveaway_id"], user_id),
            )
            participant = await cursor.fetchone()
            purchased = int(participant["purchased"]) if participant else 0
            if purchased + int(order["quantity"]) > int(giveaway["max_tickets_per_user"]):
                await db.rollback()
                return {"status": "late_or_invalid"}

            await db.execute(
                """INSERT INTO payment_events(telegram_charge_id,payload,user_id,amount,currency,processed_at)
                   VALUES(?,?,?,?,?,?)""",
                (telegram_charge_id, payload, user_id, amount, currency, now),
            )
            await db.execute(
                "UPDATE orders SET status='paid',telegram_charge_id=?,provider_charge_id=?,paid_at=? WHERE id=?",
                (telegram_charge_id, provider_charge_id, now, order["id"]),
            )
            await db.execute(
                """INSERT INTO participants(giveaway_id,user_id,tickets_count,total_paid,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(giveaway_id,user_id) DO UPDATE SET
                     tickets_count=tickets_count+excluded.tickets_count,
                     total_paid=total_paid+excluded.total_paid,
                     updated_at=excluded.updated_at""",
                (order["giveaway_id"], user_id, order["quantity"], amount, now, now),
            )
            cursor = await db.execute(
                "SELECT COALESCE(MAX(ticket_number),0) AS max_no FROM tickets WHERE giveaway_id=?",
                (order["giveaway_id"],),
            )
            next_number = int((await cursor.fetchone())["max_no"]) + 1
            numbers = list(range(next_number, next_number + int(order["quantity"])))
            await db.executemany(
                "INSERT INTO tickets(giveaway_id,user_id,ticket_number,order_id,created_at) VALUES(?,?,?,?,?)",
                [(order["giveaway_id"], user_id, number, order["id"], now) for number in numbers],
            )
            await db.commit()
            return {"status": "paid", "giveaway_id": int(order["giveaway_id"]),
                    "quantity": int(order["quantity"]), "amount": amount,
                    "ticket_numbers": numbers, "title": giveaway["title"]}

    async def expire_order_by_payload(self, payload: str) -> None:
        async with self.connection() as db:
            await db.execute(
                "UPDATE orders SET status='expired' WHERE payload=? AND status='pending'",
                (payload,),
            )
            await db.commit()

    async def expire_orders(self) -> None:
        now = iso_utc()
        async with self.connection() as db:
            await db.execute(
                """UPDATE orders SET status='expired' WHERE status='pending' AND
                   (expires_at<=? OR giveaway_id IN (SELECT id FROM giveaways WHERE status!='active' OR closes_at<=?))""",
                (now, now),
            )
            await db.execute("UPDATE orders SET status='expired' WHERE status='accepted' AND expires_at<=?", (now,))
            await db.commit()

    async def due_giveaways(self) -> list[dict[str, Any]]:
        now = iso_utc()
        async with self.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM giveaways WHERE status='active' AND closes_at<=? ORDER BY closes_at",
                (now,),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def finish_giveaway(self, giveaway_id: int) -> dict[str, Any] | None:
        """Close once, select unique winners weighted by their number of tickets."""
        import random

        async with self.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            now = iso_utc()
            cursor = await db.execute("SELECT * FROM giveaways WHERE id=?", (giveaway_id,))
            giveaway = await cursor.fetchone()
            if not giveaway or giveaway["status"] != "active" or giveaway["closes_at"] > now:
                await db.rollback()
                return None
            cursor = await db.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE giveaway_id=? AND status='accepted' AND expires_at>?",
                (giveaway_id, now),
            )
            if int((await cursor.fetchone())["n"]) > 0:
                await db.rollback()
                return None

            await db.execute(
                "UPDATE orders SET status='expired' WHERE giveaway_id=? AND status='pending'",
                (giveaway_id,),
            )
            cursor = await db.execute(
                """SELECT t.id AS ticket_id,t.ticket_number,t.user_id,u.username,u.first_name
                   FROM tickets t JOIN users u ON u.user_id=t.user_id
                   WHERE t.giveaway_id=? ORDER BY t.id""",
                (giveaway_id,),
            )
            tickets = [dict(row) for row in await cursor.fetchall()]
            random.SystemRandom().shuffle(tickets)
            chosen: list[dict[str, Any]] = []
            used_users: set[int] = set()
            for ticket in tickets:
                user_id = int(ticket["user_id"])
                if user_id in used_users:
                    continue
                used_users.add(user_id)
                chosen.append(ticket)
                if len(chosen) >= int(giveaway["winners_count"]):
                    break

            for place, winner in enumerate(chosen, start=1):
                await db.execute(
                    "INSERT INTO winners(giveaway_id,user_id,ticket_id,place,created_at) VALUES(?,?,?,?,?)",
                    (giveaway_id, winner["user_id"], winner["ticket_id"], place, now),
                )
            await db.execute(
                "UPDATE giveaways SET status='completed',updated_at=? WHERE id=?",
                (now, giveaway_id),
            )
            await db.commit()
            return {"giveaway": dict(giveaway), "winners": chosen,
                    "participants": sorted({int(ticket["user_id"]) for ticket in tickets}),
                    "winner_count": len(chosen), "ticket_count": len(tickets)}

    async def get_participant_ids(self, giveaway_id: int) -> list[int]:
        async with self.connection() as db:
            cursor = await db.execute("SELECT user_id FROM participants WHERE giveaway_id=?", (giveaway_id,))
            return [int(row[0]) for row in await cursor.fetchall()]

    async def set_results_message(self, giveaway_id: int, message_id: int) -> None:
        async with self.connection() as db:
            await db.execute("UPDATE giveaways SET results_message_id=? WHERE id=?", (message_id, giveaway_id))
            await db.commit()
