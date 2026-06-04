"""
Pure scheduling logic for recurring USDC payments.

A schedule pays a fixed amount to a payee at a fixed interval, starting at start_ts,
optionally ending at end_ts and optionally capped at max_payments. The scheduled payment
times are start_ts, start_ts + interval, start_ts + 2*interval, and so on.

`due_payments` is pure: given how many payments have already been made, it returns the
scheduled times that are now due and not yet paid. If a poll is late and several intervals
have passed, it returns all of them, in order. The engine sends one payment per due time
and advances the count, so a payment is never made twice and never skipped.
"""
from __future__ import annotations

from typing import Optional


def due_payments(
    start_ts: float,
    interval_seconds: float,
    paid_count: int,
    now: float,
    end_ts: Optional[float] = None,
    max_payments: Optional[int] = None,
) -> list[float]:
    """Return the scheduled payment times that are due (<= now) and not yet paid."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    due: list[float] = []
    i = paid_count
    while True:
        if max_payments is not None and i >= max_payments:
            break
        t = start_ts + i * interval_seconds
        if t > now:
            break
        if end_ts is not None and t > end_ts:
            break
        due.append(t)
        i += 1
    return due


def is_complete(paid_count: int, now: float, end_ts: Optional[float], max_payments: Optional[int]) -> bool:
    """A schedule is complete when it has paid its max, or its end has passed with nothing
    left due."""
    if max_payments is not None and paid_count >= max_payments:
        return True
    if end_ts is not None and now > end_ts:
        return True
    return False
