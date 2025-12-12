
import sys
import os
from dotenv import load_dotenv

load_dotenv()
os.environ["FORCE_OP_SYNC"] = "1"

# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from wpr_agent.mcp.servers.wpr_server import build_server

# FastMCP object is an ASGI app
mcp = build_server()

# FastMCP exposes .mount_asgi_app() or might be an app itself depending on version.
# Looking at wpr_server.py: app = FastMCP("wpr_router_mcp")
# FastMCP typically needs to be run via its own CLI or mounted.
# However, if we want to run it with uvicorn, we might need to extract the underlying Starlette/FastAPI app if it has one, 
# or use FastMCP's run method. 
# But the user said "use uvicorn".
# Let's assume FastMCP instance is ASGI compatible or has an attribute.
# Actually, FastMCP (from fastmcp) usually provides an ASGI app via `app` attribute or is callable?
# Let's check if we can just expose it.
# If it's the `fastmcp` library, `FastMCP` class usually has `_app` or similar if it wraps FastAPI.
# But wait, `fastmcp run` failed.
# Let's try to just expose the object. Uvicorn expects an ASGI app.
# If FastMCP isn't an ASGI app itself, this might fail.
# But let's try.

# FastMCP object is not an ASGI app itself, but exposes .sse_app for SSE transport
app = mcp.sse_app
