"""
Arc Streaming Pay: recurring and scheduled USDC payments on Arc. "Pay this address 50 USDC
every 7 days for 12 weeks." Set up a schedule, then call run_due on a cron (or your own
loop) and it sends whatever is due. It catches up if a run is late, and never pays twice.

Use it for subscriptions, payroll, vesting, allowances, or any drip of USDC. Pairs with the
rest of the agent payments stack on Arc.

Config via env:
  STREAMPAY_DB_PATH   where to keep schedules (default streampay.db)
  ARC_PRIVATE_KEY     the paying wallet's key (needed only to send)
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .store import ScheduleStore
from .engine import StreamEngine
from .arc import ArcSender

DB_PATH = os.getenv("STREAMPAY_DB_PATH", "streampay.db")

mcp = FastMCP("arc-streaming-pay")
_store = ScheduleStore(DB_PATH)
_sender = ArcSender()
_engine = StreamEngine(_store, executor=_sender.send)


@mcp.tool()
def stream_create(payee: str, amount_usdc: float, interval_seconds: float,
                  start_ts: float | None = None, end_ts: float | None = None,
                  max_payments: int | None = None, memo: str = "") -> dict:
    """Create a recurring payment schedule.

    Args:
        payee: 0x address to pay each interval
        amount_usdc: amount per payment
        interval_seconds: seconds between payments (e.g. 604800 for weekly)
        start_ts: unix time of the first payment (default now)
        end_ts: optional unix time after which no more payments are made
        max_payments: optional cap on the number of payments
        memo: a note (e.g. "payroll for X")
    """
    return _engine.create(payee, amount_usdc, interval_seconds, start_ts, end_ts, max_payments, memo)


@mcp.tool()
def stream_run_due() -> dict:
    """Send every payment that is due now across all active schedules. Call this on a cron
    or loop. Safe to call often: it only sends what is due and never double-pays."""
    return _engine.run_due()


@mcp.tool()
def stream_cancel(schedule_id: int) -> dict:
    """Cancel an active schedule. No further payments are made."""
    return _engine.cancel(schedule_id)


@mcp.tool()
def stream_get(schedule_id: int) -> dict:
    """Get a schedule with its payment history."""
    return _engine.get(schedule_id)


@mcp.tool()
def stream_list(status: str | None = None) -> dict:
    """List schedules, optionally filtered by status (active, completed, cancelled)."""
    return {"schedules": _engine.list(status)}


@mcp.tool()
def stream_wallet() -> dict:
    """The paying wallet address and whether a key is configured."""
    return {"wallet_address": _sender.address(), "configured": _sender.configured}


if __name__ == "__main__":
    mcp.run()
