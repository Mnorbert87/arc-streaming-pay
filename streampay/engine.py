"""
The streaming engine runs due payments for recurring schedules.

  executor(payee, amount) -> tx_hash   (production: the Arc sender; tests: a fake)

On `run_due`, for each active schedule it computes the payments that are now due (using the
pure scheduler), sends one per due time in order, and records each. If a send fails, it
stops that schedule for this run and leaves the rest due, so payments are never skipped or
doubled. A schedule is marked completed once it reaches its max or its end passes.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from .store import ScheduleStore
from .schedule import due_payments, is_complete

Executor = Callable[[str, float], str]


class StreamEngine:
    def __init__(self, store: ScheduleStore, executor: Executor):
        self.store = store
        self.executor = executor

    def create(self, payee: str, amount: float, interval_seconds: float,
               start_ts: Optional[float] = None, end_ts: Optional[float] = None,
               max_payments: Optional[int] = None, memo: str = "", now: Optional[float] = None) -> dict:
        now = now if now is not None else time.time()
        if amount is None or amount <= 0:
            return {"status": "error", "reason": "amount must be positive"}
        if interval_seconds is None or interval_seconds <= 0:
            return {"status": "error", "reason": "interval_seconds must be positive"}
        if not (payee or "").lower().startswith("0x") or len(payee) != 42:
            return {"status": "error", "reason": "payee must be a valid 0x address"}
        start = start_ts if start_ts is not None else now
        sid = self.store.create_schedule(payee, amount, interval_seconds, start, end_ts, max_payments, memo, now=now)
        return {"status": "active", "schedule_id": sid, "next_payment_ts": start}

    def run_due(self, now: Optional[float] = None) -> dict:
        now = now if now is not None else time.time()
        results = []
        for sch in self.store.list_schedules(status="active"):
            paid = 0
            failed = False
            due = due_payments(
                sch["start_ts"], sch["interval_seconds"], sch["paid_count"], now,
                end_ts=sch["end_ts"], max_payments=sch["max_payments"],
            )
            for scheduled_for in due:
                try:
                    tx_hash = self.executor(sch["payee"], sch["amount_usdc"])
                except Exception as e:
                    results.append({"schedule_id": sch["id"], "error": f"send failed, will retry: {e}", "paid_this_run": paid})
                    failed = True
                    break
                self.store.record_payment(sch["id"], scheduled_for, sch["amount_usdc"], tx_hash, now=now)
                paid += 1

            if not failed:
                fresh = self.store.get_schedule(sch["id"])
                if is_complete(fresh["paid_count"], now, fresh["end_ts"], fresh["max_payments"]):
                    self.store.set_status(sch["id"], "completed")
                results.append({"schedule_id": sch["id"], "paid_this_run": paid,
                                "paid_total": fresh["paid_count"], "status": self.store.get_schedule(sch["id"])["status"]})
        return {"ran": len(results), "total_paid_this_run": sum(r.get("paid_this_run", 0) for r in results), "results": results}

    def cancel(self, sid: int) -> dict:
        sch = self.store.get_schedule(sid)
        if not sch:
            return {"status": "error", "reason": f"no schedule {sid}"}
        if sch["status"] != "active":
            return {"status": sch["status"], "reason": "not active"}
        self.store.set_status(sid, "cancelled")
        return {"status": "cancelled", "schedule_id": sid}

    def get(self, sid: int) -> dict:
        sch = self.store.get_schedule(sid)
        if not sch:
            return {"status": "error", "reason": f"no schedule {sid}"}
        sch["payments"] = self.store.payments_for(sid)
        return sch

    def list(self, status: Optional[str] = None) -> list[dict]:
        return self.store.list_schedules(status)
