"""
Integration tests for the streaming engine with a fake executor: prove that due payments
fire the right number of times, catch up after a gap, never double, complete correctly,
and that a failed send is retried rather than skipped.
"""
from streampay.store import ScheduleStore
from streampay.engine import StreamEngine

PAYEE = "0x" + "a" * 40


class FakeExecutor:
    def __init__(self, fail_at=None):
        self.sent = []
        self.n = 0
        self.fail_at = fail_at

    def __call__(self, to, amount):
        self.n += 1
        if self.fail_at is not None and self.n == self.fail_at:
            raise RuntimeError("rpc down")
        self.sent.append((to, amount))
        return f"0xs{self.n}"


def _engine(tmp_path, fail_at=None):
    store = ScheduleStore(str(tmp_path / "s.db"))
    fake = FakeExecutor(fail_at=fail_at)
    return StreamEngine(store, fake), store, fake


def test_create_rejects_bad_input(tmp_path):
    eng, _, _ = _engine(tmp_path)
    assert eng.create(PAYEE, 0, 10)["status"] == "error"
    assert eng.create(PAYEE, 5, 0)["status"] == "error"
    assert eng.create("bad", 5, 10)["status"] == "error"


def test_one_payment_due_at_start(tmp_path):
    eng, store, fake = _engine(tmp_path)
    eng.create(PAYEE, 5, interval_seconds=10, start_ts=100, now=100)
    res = eng.run_due(now=100)
    assert res["total_paid_this_run"] == 1
    assert fake.sent == [(PAYEE.lower(), 5)]


def test_catches_up_missed_intervals(tmp_path):
    eng, store, fake = _engine(tmp_path)
    eng.create(PAYEE, 1, interval_seconds=10, start_ts=0, now=0)
    res = eng.run_due(now=35)  # due at 0,10,20,30 -> 4 payments
    assert res["total_paid_this_run"] == 4
    assert len(fake.sent) == 4


def test_no_double_on_second_run(tmp_path):
    eng, store, fake = _engine(tmp_path)
    eng.create(PAYEE, 1, interval_seconds=10, start_ts=0, now=0)
    eng.run_due(now=15)   # pays 0,10
    before = len(fake.sent)
    eng.run_due(now=15)   # nothing new
    assert len(fake.sent) == before


def test_completes_at_max_payments(tmp_path):
    eng, store, fake = _engine(tmp_path)
    sid = eng.create(PAYEE, 1, interval_seconds=10, start_ts=0, max_payments=2, now=0)["schedule_id"]
    eng.run_due(now=1000)
    assert len(fake.sent) == 2
    assert store.get_schedule(sid)["status"] == "completed"


def test_cancel_stops_future_payments(tmp_path):
    eng, store, fake = _engine(tmp_path)
    sid = eng.create(PAYEE, 1, interval_seconds=10, start_ts=0, now=0)["schedule_id"]
    eng.run_due(now=5)   # pays at 0
    eng.cancel(sid)
    eng.run_due(now=100)  # cancelled, nothing
    assert len(fake.sent) == 1


def test_failed_send_is_retried_not_skipped(tmp_path):
    # fail on the 2nd send; the first persists, the run stops, a later run retries the rest
    eng, store, fake = _engine(tmp_path, fail_at=2)
    sid = eng.create(PAYEE, 1, interval_seconds=10, start_ts=0, now=0)["schedule_id"]
    eng.run_due(now=35)  # due 0,10,20,30; pays 0, fails on 10
    assert store.get_schedule(sid)["paid_count"] == 1
    # the failure was the 2nd call; subsequent calls succeed
    res = eng.run_due(now=35)
    assert store.get_schedule(sid)["paid_count"] == 4  # caught up the remaining 3
