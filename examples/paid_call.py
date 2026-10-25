"""Make one real paid call to `brief` (0.01 USDC on Base) and print the settlement proof.

    export X402_PRIVATE_KEY=0x...   # a wallet holding at least 0.01 USDC on Base
    python examples/paid_call.py
"""
import json
from blockchainiq_langchain import BlockchainIQBriefTool

result = json.loads(BlockchainIQBriefTool().invoke({}))
print(json.dumps(result.get("payment"), indent=2))
print("transaction:", (result.get("payment") or {}).get("transaction"))
print("coins:", [c.get("symbol") for c in result["data"].get("data", {}).get("coins", [])])
