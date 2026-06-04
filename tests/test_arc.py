"""
Tests for the sender's nonce manager and EIP-1559 fee logic, with rpc monkeypatched so no
network is touched. The nonce manager is the fix for the batch-send bug: several sends in
one run must get consecutive nonces, not the same lagging "pending" value.
"""
import pytest

from streampay import arc as arcmod
from streampay.arc import ArcSender, MIN_BASE_FEE_WEI, DEFAULT_PRIORITY_WEI

ADDR = "0x" + "a" * 40


class FakeRPC:
    """Stand-in for the JSON-RPC: a fixed pending count and a base fee."""
    def __init__(self, pending=5, base_fee=10 * 10**9, priority=2 * 10**9):
        self.pending = pending
        self.base_fee = base_fee
        self.priority = priority

    def __call__(self, method, params):
        if method == "eth_getTransactionCount":
            return hex(self.pending)
        if method == "eth_getBlockByNumber":
            return {"baseFeePerGas": hex(self.base_fee)}
        if method == "eth_maxPriorityFeePerGas":
            return hex(self.priority)
        raise AssertionError(f"unexpected rpc {method}")


def test_batch_nonces_are_consecutive(monkeypatch):
    monkeypatch.setattr(arcmod, "rpc", FakeRPC(pending=5))
    s = ArcSender(private_key="0x" + "1" * 64)
    n1 = s._reserve_nonce(ADDR)
    n2 = s._reserve_nonce(ADDR)
    n3 = s._reserve_nonce(ADDR)
    assert [n1, n2, n3] == [5, 6, 7]  # not [5, 5, 5]


def test_nonce_follows_chain_if_chain_jumps_ahead(monkeypatch):
    fake = FakeRPC(pending=5)
    monkeypatch.setattr(arcmod, "rpc", fake)
    s = ArcSender(private_key="0x" + "1" * 64)
    assert s._reserve_nonce(ADDR) == 5
    fake.pending = 9  # an external tx landed
    assert s._reserve_nonce(ADDR) == 9


def test_fees_respect_min_base_fee(monkeypatch):
    # base fee reported below Arc's 20 Gwei minimum -> clamp up
    monkeypatch.setattr(arcmod, "rpc", FakeRPC(base_fee=1 * 10**9, priority=2 * 10**9))
    s = ArcSender(private_key="0x" + "1" * 64)
    max_fee, priority = s._fees()
    assert priority == 2 * 10**9
    assert max_fee == MIN_BASE_FEE_WEI * 2 + priority


def test_fees_priority_fallback_when_zero(monkeypatch):
    monkeypatch.setattr(arcmod, "rpc", FakeRPC(base_fee=30 * 10**9, priority=0))
    s = ArcSender(private_key="0x" + "1" * 64)
    _, priority = s._fees()
    assert priority == DEFAULT_PRIORITY_WEI


def test_send_builds_type2_and_resyncs_nonce_on_failure(monkeypatch):
    fake = FakeRPC(pending=3)
    sent = {}

    def rpc_with_failing_broadcast(method, params):
        if method == "eth_sendRawTransaction":
            sent["raw"] = params[0]
            raise RuntimeError("broadcast rejected")
        return fake(method, params)

    monkeypatch.setattr(arcmod, "rpc", rpc_with_failing_broadcast)
    s = ArcSender(private_key="0x" + "1" * 64)
    s._reserve_nonce(ADDR)  # advance local nonce to 3 -> next would be 4
    with pytest.raises(RuntimeError):
        s.send(ADDR, 1.0)
    # the signed raw is a type-2 (EIP-1559) tx: typed envelope starts with 0x02
    assert sent["raw"].startswith("0x02")
    # after failure the local nonce was reset so the next send resyncs from chain
    assert s._next_nonce is None
