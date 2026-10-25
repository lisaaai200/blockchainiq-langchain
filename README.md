# blockchainiq-langchain

LangChain tools for [Blockchain IQ](https://www.blockchainiq.co)'s pay-per-call crypto data API. No account and no API key: when the API answers HTTP 402, the tool signs an [x402](https://x402.org) "exact" payment (an EIP-3009 USDC authorization on Base), retries once, and returns the JSON plus the settlement proof.

| Tool | Resource | Price |
| --- | --- | --- |
| `blockchainiq_brief` | BTC/ETH/SOL/XRP prices and moves, events in the next 48h, risk flags | 0.01 USDC |
| `blockchainiq_event_risk` | Macro, central bank, Treasury and crypto milestones, 7 days ahead by default | 0.05 USDC |

## Install

```bash
pip install -e .
export X402_PRIVATE_KEY=0x...   # a dedicated wallet holding a little USDC on Base
```

The payer needs only USDC; the seller's facilitator submits the transfer and pays the gas.

## Use with an agent

```python
from blockchainiq_langchain import blockchainiq_tools
tools = blockchainiq_tools()            # both tools share one x402 client
agent = create_react_agent(llm, tools)  # any LangChain / LangGraph agent
```

Or call a tool directly:

```python
from blockchainiq_langchain import BlockchainIQBriefTool
print(BlockchainIQBriefTool().invoke({}))
# {"data": {...}, "payment": {"amount_usdc_atomic": "10000", "transaction": "0x...", "network": "eip155:8453"}}
```

`examples/paid_call.py` makes one real paid call and prints the transaction hash.

## Safety

- `X402Client(max_amount=50_000)` refuses any price above 0.05 USDC (atomic units, 6 decimals) before signing anything.
- Only scheme `exact` on Base mainnet (`eip155:8453`) or Base Sepolia (`eip155:84532`) is accepted.
- Each authorization uses a fresh random nonce and expires after the seller's `maxTimeoutSeconds`.
- Use a dedicated low-balance wallet; never put a main wallet key in an agent's environment.

## Tests

```bash
pip install -e ".[test]" && pytest
```

The tests run offline against a fake seller that returns a real-shaped 402, recovers the EIP-712 signature to check it, and settles.

## Live proof: one real paid call

On 25 Oct 2026 at 03:14:59 UTC (block 53054376), `BlockchainIQBriefTool` made one real paid call to `brief` on Base mainnet.

- Settlement tx: [`0x4a0f506da12bff6322e8295c7cb2db863e5f6694fd9dea6030c5c002c42e7b7e`](https://basescan.org/tx/0x4a0f506da12bff6322e8295c7cb2db863e5f6694fd9dea6030c5c002c42e7b7e)
- Payer: `0x460DfACb909637F2E971b15e19727aDB4A2adBd2` → payTo `0x617dA9383fbA67e86137BC4924b8b7E400fB7C9e`
- Amount: 10000 atomic USDC (0.01 USDC). The facilitator submitted the transfer and paid the gas; the payer sent no transaction of its own.
- Tool output (`payment` field): `{"amount_usdc_atomic": "10000", "transaction": "0x4a0f506d…7b7e", "network": "eip155:8453"}`
- Response excerpt: `asOf` 2026-10-25T03:14:56.595Z, BTC 80882, ETH 2364.19, SOL 102.38, XRP 1.31, 1 event in the next 48h ("Ethereum Glamsterdam upgrade activates on Hoodi testnet"), 0 flags.

## Who built this

This project is AI-built: it was written, tested and published by Genie, an AI agent running an openly AI-operated builder account (GitHub `lisaaai200`), with a human owner approving any spending. MIT licensed.

