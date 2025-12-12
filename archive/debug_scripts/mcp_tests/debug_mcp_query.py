import os
import sys
import asyncio
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from dotenv import load_dotenv
load_dotenv()

# Ensure MCP env vars are set for the client
os.environ["MCP_OP_TRANSPORT"] = "http"
os.environ["MCP_OP_URL"] = "http://localhost:8766/sse"

from wpr_agent.mcp.openproject_client import _mk_client

async def main():
    print("Checking wpr.query_wpr_orders...")
    try:
        client = _mk_client()
        async with client:
            print("Connected to MCP Server.")
            res = await client.call_tool("wpr.query_wpr_orders", {"batch_id": "20251201211608"})
            print(f"Result: {res.keys() if isinstance(res, dict) else res}")
    except Exception as e:
        print(f"Call Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
