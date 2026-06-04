"""SQLite persistence for recurring payment schedules and their payment log."""
from __future__ import annotations

import sqlite3
import time
from typing import Optional


class ScheduleStore:
    def __init__(self, path: str = "streampay.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                payee TEXT NOT NULL,
                amount_usdc REAL NOT NULL,
                interval_seconds REAL NOT NULL,
                start_ts REAL NOT NULL,
                end_ts REAL,
                max_payments INTEGER,
                paid_count INTEGER NOT NULL DEFAULT 0,
                last_paid_ts REAL,
                status TEXT NOT NULL DEFAULT 'active',
                memo TEXT
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                ts REAL NOT NULL,
                scheduled_for REAL NOT NULL,
                amount_usdc REAL NOT NULL,
                tx_hash TEXT
            );
            """
        )
        self.conn.commit()

    def create_schedule(self, payee: str, amount: float, interval_seconds: float, start_ts: float,
                        end_ts: Optional[float] = None, max_payments: Optional[int] = None,
                        memo: str = "", now: Optional[float] = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO schedules (ts, payee, amount_usdc, interval_seconds, start_ts, end_ts, max_payments, memo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (now if now is not None else time.time(), payee.lower(), amount, interval_seconds, start_ts, end_ts, max_payments, memo),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_schedule(self, sid: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM schedules WHERE id = ?", (sid,)).fetchone()
        return dict(row) if row else None

    def list_schedules(self, status: Optional[str] = None) -> list[dict]:
        if status:
            rows = self.conn.execute("SELECT * FROM schedules WHERE status = ? ORDER BY id DESC", (status,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM schedules ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def record_payment(self, schedule_id: int, scheduled_for: float, amount: float, tx_hash: Optional[str], now: Optional[float] = None) -> None:
        n = now if now is not None else time.time()
        self.conn.execute(
            "INSERT INTO payments (schedule_id, ts, scheduled_for, amount_usdc, tx_hash) VALUES (?, ?, ?, ?, ?)",
            (schedule_id, n, scheduled_for, amount, tx_hash),
        )
        self.conn.execute(
            "UPDATE schedules SET paid_count = paid_count + 1, last_paid_ts = ? WHERE id = ?",
            (n, schedule_id),
        )
        self.conn.commit()

    def set_status(self, sid: int, status: str) -> None:
        self.conn.execute("UPDATE schedules SET status = ? WHERE id = ?", (status, sid))
        self.conn.commit()

    def payments_for(self, sid: int) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM payments WHERE schedule_id = ? ORDER BY id", (sid,)).fetchall()]

    def close(self) -> None:
        self.conn.close()
