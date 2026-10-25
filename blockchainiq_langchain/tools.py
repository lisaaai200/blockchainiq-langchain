"""LangChain tools for Blockchain IQ's pay-per-call crypto data API (x402 on Base)."""
from __future__ import annotations

import json
from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from .x402_client import X402Client

BASE_URL = "https://www.blockchainiq.co/api/x402/v1"


class _NoArgs(BaseModel):
    pass


class _EventRiskArgs(BaseModel):
    days: Optional[int] = Field(
        default=None, description="How many days ahead to look (API default is 7).")


class _PaidTool(BaseTool):
    base_url: str = BASE_URL
    include_settlement: bool = True
    _client: X402Client = PrivateAttr()

    def __init__(self, client: Optional[X402Client] = None, **kw):
        super().__init__(**kw)
        self._client = client or X402Client()

    def _call(self, path: str, params: Optional[dict] = None) -> str:
        res = self._client.get(f"{self.base_url}/{path}", params=params)
        out = {"data": res.data}
        if self.include_settlement and res.settlement:
            out["payment"] = {"amount_usdc_atomic": res.paid_amount,
                              "transaction": res.transaction,
                              "network": res.settlement.get("network")}
        return json.dumps(out)


class BlockchainIQBriefTool(_PaidTool):
    name: str = "blockchainiq_brief"
    description: str = (
        "Crypto market brief: BTC, ETH, SOL and XRP prices with 24h/7d/30d moves, "
        "scheduled macro and crypto events in the next 48 hours, and short risk flags. "
        "Takes no input. Costs 0.01 USDC per call, paid automatically via x402 on Base.")
    args_schema: Type[BaseModel] = _NoArgs

    def _run(self, **_: object) -> str:
        return self._call("brief")


class BlockchainIQEventRiskTool(_PaidTool):
    name: str = "blockchainiq_event_risk"
    description: str = (
        "Upcoming event risk: US data releases, central bank decisions, Treasury auctions "
        "and dated crypto/regulatory milestones (7 days ahead by default), each with its "
        "official source. Costs 0.05 USDC per call, paid automatically via x402 on Base.")
    args_schema: Type[BaseModel] = _EventRiskArgs

    def _run(self, days: Optional[int] = None) -> str:
        return self._call("event-risk", {"days": days} if days else None)


def blockchainiq_tools(client: Optional[X402Client] = None) -> list[BaseTool]:
    client = client or X402Client()
    return [BlockchainIQBriefTool(client=client), BlockchainIQEventRiskTool(client=client)]
