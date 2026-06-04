"""
Arc testnet sender: signs and broadcasts a native USDC transfer.

Arc specifics handled here:
  - USDC is the native gas token; a payment is a native value transfer with 18 decimals.
  - Arc uses EIP-1559 (type 2) transactions with a 20 Gwei minimum base fee, so we send
    type 2 with maxFeePerGas / maxPriorityFeePerGas, not a legacy gasPrice.
  - A small in-process nonce manager so several sends in one batch (e.g. a streaming
    catch-up) get consecutive nonces instead of all reading the same lagging "pending"
    count. On any send failure the nonce is resynced from chain on the next attempt.

The private key is read from the environment and never logged or returned.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

RPC_URL = os.getenv("ARC_TESTNET_RPC_URL", "https://rpc.testnet.arc.network")
CHAIN_ID = int(os.getenv("ARC_CHAIN_ID", "5042002"))
EXPLORER = "https://testnet.arcscan.app"
NATIVE_DECIMALS = 18
MIN_BASE_FEE_WEI = 20 * 10 ** 9   # Arc minimum base fee: 20 Gwei
DEFAULT_PRIORITY_WEI = 10 ** 9    # 1 Gwei fallback tip


def rpc(method: str, params: list) -> object:
    with httpx.Client(timeout=20.0) as client:
        r = client.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"RPC error on {method}: {data['error']}")
        return data["result"]


def _to_int(h) -> int:
    return int(h, 16) if isinstance(h, str) else int(h)


def get_balance_usdc(address: str) -> float:
    return _to_int(rpc("eth_getBalance", [address, "latest"])) / 10 ** NATIVE_DECIMALS


class ArcSender:
    def __init__(self, private_key: Optional[str] = None):
        self.private_key = private_key or os.getenv("ARC_PRIVATE_KEY")
        self._next_nonce: Optional[int] = None

    @property
    def configured(self) -> bool:
        return bool(self.private_key)

    def address(self) -> Optional[str]:
        if not self.private_key:
            return None
        from eth_account import Account
        return Account.from_key(self.private_key).address

    def _reserve_nonce(self, address: str) -> int:
        """Next nonce to use. Tracks locally so a batch of sends increments correctly, but
        never goes below the chain's pending count (so external txs are respected)."""
        chain_pending = _to_int(rpc("eth_getTransactionCount", [address, "pending"]))
        if self._next_nonce is None or chain_pending > self._next_nonce:
            self._next_nonce = chain_pending
        n = self._next_nonce
        self._next_nonce += 1
        return n

    def _fees(self) -> tuple[int, int]:
        """EIP-1559 fees: a priority tip and a max fee with headroom over the base fee,
        respecting Arc's 20 Gwei minimum base fee."""
        try:
            block = rpc("eth_getBlockByNumber", ["latest", False])
            base = _to_int(block.get("baseFeePerGas", "0x0"))
        except Exception:
            base = 0
        base = max(base, MIN_BASE_FEE_WEI)
        try:
            priority = _to_int(rpc("eth_maxPriorityFeePerGas", []))
        except Exception:
            priority = DEFAULT_PRIORITY_WEI
        if priority <= 0:
            priority = DEFAULT_PRIORITY_WEI
        max_fee = base * 2 + priority
        return max_fee, priority

    def send(self, to: str, amount_usdc: float) -> str:
        if not self.private_key:
            raise RuntimeError("ARC_PRIVATE_KEY not set; cannot send")
        from eth_account import Account
        from eth_utils import to_checksum_address

        acct = Account.from_key(self.private_key)
        max_fee, priority = self._fees()
        nonce = self._reserve_nonce(acct.address)
        tx = {
            "to": to_checksum_address(to),
            "value": int(round(amount_usdc * 10 ** NATIVE_DECIMALS)),
            "gas": 21000,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority,
            "nonce": nonce,
            "chainId": CHAIN_ID,
            "type": 2,
        }
        signed = Account.sign_transaction(tx, self.private_key)
        raw = signed.raw_transaction.hex()
        if not raw.startswith("0x"):
            raw = "0x" + raw
        try:
            return rpc("eth_sendRawTransaction", [raw])
        except Exception:
            # on failure, force a nonce resync from chain on the next attempt
            self._next_nonce = None
            raise
