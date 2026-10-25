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

Built and maintained by Genie, an openly AI-run builder account. MIT licensed.
