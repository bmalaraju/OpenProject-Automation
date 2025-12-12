import os
import sys
import asyncio
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from dotenv import load_dotenv
load_dotenv()

# Force stdio transport to trigger in-process server build (though we will build it manually here)
os.environ["MCP_OP_TRANSPORT"] = "stdio"

from wpr_agent.mcp.servers.wpr_server import build_server
from fastmcp import Client

async def main():
    print("DEBUG: Building wpr_server in-process...")
    try:
        app = build_server()
        print("DEBUG: Server built successfully.")
        with open("debug_dir.txt", "w") as f:
            f.write(str(dir(app)))
        
        # Create a client connected directly to the app
        client = Client(app)
        
        print("DEBUG: Calling observability.tracing_config_summary...")
        async with client:
            res = await client.call_tool("observability.tracing_config_summary", {"payload": {}})
            print(f"Result: {res}")
            
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
