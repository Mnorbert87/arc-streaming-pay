"""Tests for the pure recurring-payment scheduling logic."""
import pytest

from streampay.schedule import due_payments, is_complete


def test_nothing_due_before_start():
    assert due_payments(start_ts=100, interval_seconds=10, paid_count=0, now=50) == []


def test_first_payment_due_at_start():
    assert due_payments(start_ts=100, interval_seconds=10, paid_count=0, now=100) == [100]


def test_catches_up_multiple_missed_intervals():
    # start 0, interval 10, now 35, nothing paid -> due at 0,10,20,30
    assert due_payments(start_ts=0, interval_seconds=10, paid_count=0, now=35) == [0, 10, 20, 30]


def test_skips_already_paid():
    # 2 already paid (0,10); now 35 -> due 20,30
    assert due_payments(start_ts=0, interval_seconds=10, paid_count=2, now=35) == [20, 30]


def test_respects_max_payments():
    assert due_payments(start_ts=0, interval_seconds=10, paid_count=0, now=1000, max_payments=3) == [0, 10, 20]


def test_respects_end_ts():
    assert due_payments(start_ts=0, interval_seconds=10, paid_count=0, now=1000, end_ts=25) == [0, 10, 20]


def test_no_double_when_caught_up():
    assert due_payments(start_ts=0, interval_seconds=10, paid_count=4, now=35) == []


def test_zero_interval_raises():
    with pytest.raises(ValueError):
        due_payments(start_ts=0, interval_seconds=0, paid_count=0, now=10)


def test_is_complete_by_max():
    assert is_complete(paid_count=3, now=10, end_ts=None, max_payments=3) is True


def test_is_complete_by_end():
    assert is_complete(paid_count=1, now=100, end_ts=50, max_payments=None) is True


def test_not_complete_when_running():
    assert is_complete(paid_count=1, now=10, end_ts=100, max_payments=5) is False
