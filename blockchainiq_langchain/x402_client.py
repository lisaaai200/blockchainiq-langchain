"""Minimal x402 v2 client for the "exact" scheme on EVM (EIP-3009 USDC).

The payer signs a TransferWithAuthorization off-chain; the seller's
facilitator settles it on Base and pays the gas. The wallet only needs the
USDC amount being paid (0.01 USDC for `brief`).
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests
from eth_account import Account
from eth_account.messages import encode_typed_data

X402_VERSION = 2
SUPPORTED_NETWORKS = {"eip155:8453": 8453, "eip155:84532": 84532}


class X402Error(RuntimeError):
    pass


def b64json_decode(value: str) -> dict:
    return json.loads(base64.b64decode(value).decode())


def b64json_encode(obj: dict) -> str:
    return base64.b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()


@dataclass
class PaidResponse:
    status: int
    data: Any
    settlement: Optional[dict]
    paid_amount: Optional[str]

    @property
    def transaction(self) -> Optional[str]:
        return (self.settlement or {}).get("transaction")


def choose_requirement(required: dict, max_amount: int) -> dict:
    for req in required.get("accepts", []):
        if req.get("scheme") != "exact" or req.get("network") not in SUPPORTED_NETWORKS:
            continue
        if int(req["amount"]) > max_amount:
            raise X402Error(
                f"price {req['amount']} exceeds max_amount {max_amount} (atomic USDC units)"
            )
        return req
    raise X402Error("no supported payment option (need scheme 'exact' on Base)")


def sign_payment(account, required: dict, req: dict, now: Optional[int] = None) -> dict:
    now = int(time.time()) if now is None else now
    authorization = {
        "from": account.address,
        "to": req["payTo"],
        "value": str(req["amount"]),
        "validAfter": str(now - 600),
        "validBefore": str(now + int(req.get("maxTimeoutSeconds", 300))),
        "nonce": "0x" + secrets.token_hex(32),
    }
    extra = req.get("extra") or {}
    typed = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": extra.get("name", "USD Coin"),
            "version": extra.get("version", "2"),
            "chainId": SUPPORTED_NETWORKS[req["network"]],
            "verifyingContract": req["asset"],
        },
        "message": {
            "from": authorization["from"],
            "to": authorization["to"],
            "value": int(authorization["value"]),
            "validAfter": int(authorization["validAfter"]),
            "validBefore": int(authorization["validBefore"]),
            "nonce": bytes.fromhex(authorization["nonce"][2:]),
        },
    }
    signed = account.sign_message(encode_typed_data(full_message=typed))
    sig = signed.signature.hex()
    return {
        "x402Version": X402_VERSION,
        "resource": required.get("resource"),
        "accepted": req,
        "payload": {"signature": sig if sig.startswith("0x") else "0x" + sig,
                    "authorization": authorization},
    }


class X402Client:
    """GET a URL, and if it answers 402, pay once with the given key and retry."""

    def __init__(self, private_key: Optional[str] = None, max_amount: int = 50_000,
                 session: Optional[requests.Session] = None,
                 clock: Callable[[], int] = lambda: int(time.time())):
        key = private_key or os.environ.get("X402_PRIVATE_KEY")
        self.account = Account.from_key(key) if key else None
        self.max_amount = max_amount  # atomic USDC units, 50_000 = $0.05
        self.http = session or requests.Session()
        self.clock = clock

    def get(self, url: str, params: Optional[dict] = None, timeout: float = 30) -> PaidResponse:
        first = self.http.get(url, params=params, timeout=timeout)
        if first.status_code != 402:
            return PaidResponse(first.status_code, _json(first), None, None)
        if self.account is None:
            raise X402Error("payment required but no private key configured (X402_PRIVATE_KEY)")
        header = first.headers.get("PAYMENT-REQUIRED")
        required = b64json_decode(header) if header else _json(first)
        req = choose_requirement(required, self.max_amount)
        payment = sign_payment(self.account, required, req, now=self.clock())
        paid = self.http.get(url, params=params, timeout=timeout,
                             headers={"PAYMENT-SIGNATURE": b64json_encode(payment)})
        settle_hdr = paid.headers.get("PAYMENT-RESPONSE")
        settlement = b64json_decode(settle_hdr) if settle_hdr else None
        if paid.status_code >= 400:
            reason = paid.text[:300]
            again = paid.headers.get("PAYMENT-REQUIRED")
            if again:
                try:
                    reason = b64json_decode(again).get("error") or reason
                except ValueError:
                    pass
            raise X402Error(f"paid request failed: HTTP {paid.status_code} {reason}")
        return PaidResponse(paid.status_code, _json(paid), settlement, req["amount"])


def _json(resp) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text
