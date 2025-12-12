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
    print("Checking MCP Server Health...")
    try:
        client = _mk_client()
        async with client:
            print("Connected to MCP Server.")
            # Call a simple tool that doesn't depend on complex logic
            res = await client.call_tool("observability.tracing_config_summary", {"payload": {}})
            print(f"Result: {res}")
    except Exception as e:
        print(f"MCP Health Check Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
