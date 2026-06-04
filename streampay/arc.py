"""
Arc testnet sender for releasing a verified payment. Same signing path as the rest of the
stack: native USDC transfer, key from the environment, checksummed recipient.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

RPC_URL = os.getenv("ARC_TESTNET_RPC_URL", "https://rpc.testnet.arc.network")
CHAIN_ID = int(os.getenv("ARC_CHAIN_ID", "5042002"))
EXPLORER = "https://testnet.arcscan.app"
NATIVE_DECIMALS = 18


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


class ArcSender:
    def __init__(self, private_key: Optional[str] = None):
        self.private_key = private_key or os.getenv("ARC_PRIVATE_KEY")

    @property
    def configured(self) -> bool:
        return bool(self.private_key)

    def address(self) -> Optional[str]:
        if not self.private_key:
            return None
        from eth_account import Account
        return Account.from_key(self.private_key).address

    def send(self, to: str, amount_usdc: float) -> str:
        if not self.private_key:
            raise RuntimeError("ARC_PRIVATE_KEY not set; cannot send")
        from eth_account import Account
        from eth_utils import to_checksum_address

        acct = Account.from_key(self.private_key)
        nonce = _to_int(rpc("eth_getTransactionCount", [acct.address, "pending"]))
        gas_price = _to_int(rpc("eth_gasPrice", []))
        value = int(round(amount_usdc * 10 ** NATIVE_DECIMALS))
        tx = {
            "to": to_checksum_address(to),
            "value": value,
            "gas": 21000,
            "gasPrice": gas_price,
            "nonce": nonce,
            "chainId": CHAIN_ID,
        }
        signed = Account.sign_transaction(tx, self.private_key)
        raw = signed.raw_transaction.hex()
        if not raw.startswith("0x"):
            raw = "0x" + raw
        return rpc("eth_sendRawTransaction", [raw])
