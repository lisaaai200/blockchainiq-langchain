import json

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

from blockchainiq_langchain import (BlockchainIQBriefTool, BlockchainIQEventRiskTool,
                                    X402Client, X402Error, blockchainiq_tools)
from blockchainiq_langchain.x402_client import b64json_decode, b64json_encode, sign_payment

KEY = "0x" + "11" * 32  # throwaway test key, never funded
ACCT = Account.from_key(KEY)
REQ = {"scheme": "exact", "network": "eip155:8453", "amount": "10000",
       "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
       "payTo": "0x617dA9383fbA67e86137BC4924b8b7E400fB7C9e",
       "maxTimeoutSeconds": 300, "extra": {"name": "USD Coin", "version": "2"}}
REQUIRED = {"x402Version": 2, "error": "Payment required",
            "resource": {"url": "https://www.blockchainiq.co/api/x402/v1/brief"},
            "accepts": [REQ]}
BRIEF = {"source": "Blockchain IQ", "data": {"coins": [{"symbol": "btc", "price": 1}]}}


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeSeller:
    """Answers 402 without a payment header, verifies the signature, then settles."""

    def __init__(self, required=REQUIRED, fail_paid=False):
        self.required, self.fail_paid, self.calls = required, fail_paid, []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params, headers))
        if not headers or "PAYMENT-SIGNATURE" not in headers:
            return Resp(402, {"error": "Payment required"},
                        {"PAYMENT-REQUIRED": b64json_encode(self.required)})
        if self.fail_paid:
            return Resp(402, {"error": "invalid payment"})
        payment = b64json_decode(headers["PAYMENT-SIGNATURE"])
        assert recover(payment) == payment["payload"]["authorization"]["from"]
        settle = {"success": True, "transaction": "0xabc", "network": "eip155:8453",
                  "payer": payment["payload"]["authorization"]["from"]}
        return Resp(200, BRIEF, {"PAYMENT-RESPONSE": b64json_encode(settle)})


def recover(payment):
    a, req = payment["payload"]["authorization"], payment["accepted"]
    typed = {
        "types": {"EIP712Domain": [{"name": "name", "type": "string"},
                                   {"name": "version", "type": "string"},
                                   {"name": "chainId", "type": "uint256"},
                                   {"name": "verifyingContract", "type": "address"}],
                  "TransferWithAuthorization": [{"name": n, "type": t} for n, t in [
                      ("from", "address"), ("to", "address"), ("value", "uint256"),
                      ("validAfter", "uint256"), ("validBefore", "uint256"),
                      ("nonce", "bytes32")]]},
        "primaryType": "TransferWithAuthorization",
        "domain": {"name": "USD Coin", "version": "2", "chainId": 8453,
                   "verifyingContract": req["asset"]},
        "message": {"from": a["from"], "to": a["to"], "value": int(a["value"]),
                    "validAfter": int(a["validAfter"]), "validBefore": int(a["validBefore"]),
                    "nonce": bytes.fromhex(a["nonce"][2:])}}
    return Account.recover_message(encode_typed_data(full_message=typed),
                                   signature=payment["payload"]["signature"])


def client(seller, **kw):
    return X402Client(private_key=KEY, session=seller, clock=lambda: 1_000_000, **kw)


def test_signature_recovers_to_payer():
    p = sign_payment(ACCT, REQUIRED, REQ, now=1_000_000)
    assert recover(p) == ACCT.address
    a = p["payload"]["authorization"]
    assert a["to"] == REQ["payTo"] and a["value"] == "10000"
    assert int(a["validBefore"]) == 1_000_300 and int(a["validAfter"]) < 1_000_000
    assert p["x402Version"] == 2 and p["accepted"] == REQ


def test_nonce_is_unique():
    n1 = sign_payment(ACCT, REQUIRED, REQ)["payload"]["authorization"]["nonce"]
    n2 = sign_payment(ACCT, REQUIRED, REQ)["payload"]["authorization"]["nonce"]
    assert n1 != n2 and len(n1) == 66


def test_brief_tool_pays_once_and_returns_settlement():
    seller = FakeSeller()
    out = json.loads(BlockchainIQBriefTool(client=client(seller)).invoke({}))
    assert out["data"] == BRIEF
    assert out["payment"]["transaction"] == "0xabc"
    assert out["payment"]["amount_usdc_atomic"] == "10000"
    assert len(seller.calls) == 2 and seller.calls[0][0].endswith("/brief")


def test_event_risk_passes_days():
    seller = FakeSeller()
    BlockchainIQEventRiskTool(client=client(seller)).invoke({"days": 3})
    assert seller.calls[0][0].endswith("/event-risk") and seller.calls[0][1] == {"days": 3}


def test_price_cap_blocks_overpriced_resource():
    seller = FakeSeller()
    with pytest.raises(X402Error, match="exceeds"):
        client(seller, max_amount=5_000).get("https://x/brief")
    assert len(seller.calls) == 1  # never sent a payment


def test_unsupported_network_rejected():
    bad = dict(REQUIRED, accepts=[dict(REQ, network="solana:mainnet")])
    with pytest.raises(X402Error, match="no supported"):
        client(FakeSeller(required=bad)).get("https://x/brief")


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("X402_PRIVATE_KEY", raising=False)
    c = X402Client(session=FakeSeller())
    with pytest.raises(X402Error, match="no private key"):
        c.get("https://x/brief")


def test_rejected_payment_raises():
    with pytest.raises(X402Error, match="paid request failed"):
        client(FakeSeller(fail_paid=True)).get("https://x/brief")


def test_free_response_passes_through():
    class Free:
        def get(self, *a, **k):
            return Resp(200, {"ok": True})
    r = X402Client(session=Free()).get("https://x/catalogue")
    assert r.data == {"ok": True} and r.settlement is None


def test_toolkit_shares_client_and_names():
    tools = blockchainiq_tools(client(FakeSeller()))
    assert [t.name for t in tools] == ["blockchainiq_brief", "blockchainiq_event_risk"]
