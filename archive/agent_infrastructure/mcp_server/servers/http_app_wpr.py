from __future__ import annotations

"""
ASGI app to expose the WPR MCP server over HTTP (streamable).

Run:
  uvicorn wpr_agent.mcp.servers.http_app_wpr:app --host 0.0.0.0 --port 8766
"""

try:
    from fastmcp.server.server import create_streamable_http_app  # type: ignore
except Exception as ex:  # pragma: no cover
    raise RuntimeError(f"fastmcp does not support HTTP server features: {ex}")

from wpr_agent.mcp.servers.wpr_server import build_server  # type: ignore

app = create_streamable_http_app(build_server(), "/sse")  # type: ignore
