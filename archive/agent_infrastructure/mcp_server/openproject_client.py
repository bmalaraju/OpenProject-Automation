from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None

from wpr_agent.router.utils import log_kv


class McpUnavailable(Exception):
    pass


def _mk_client() -> Any:
    import os
    transport = os.getenv("MCP_OP_TRANSPORT", "").strip().lower()
    try:
        import fastmcp  # type: ignore
    except Exception as ex:  # pragma: no cover
        raise McpUnavailable(f"fastmcp not installed: {ex}")
    if transport == "stdio":
        try:
            # In-process FastMCP app for local dev
            from wpr_agent.mcp.servers.openproject_server import build_server  # type: ignore
            server_app = build_server()
            return fastmcp.Client(server_app, timeout=float(os.getenv("MCP_OP_TIMEOUT_SEC", "30")))
        except Exception as ex:  # pragma: no cover
            raise McpUnavailable(f"failed to init OP stdio client: {ex}")
    if transport in {"ws", "http", "https"}:
        url = os.getenv("MCP_OP_URL", "").strip()
        print(f"DEBUG: MCP Client Init - Transport: {transport}, URL: {url}")
        if not url:
            raise McpUnavailable("MCP_OP_URL not set for URL transport")
        return fastmcp.Client(url, timeout=float(os.getenv("MCP_OP_TIMEOUT_SEC", "30")))
    raise McpUnavailable("unsupported or missing MCP_OP_TRANSPORT configuration")


def _call_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    tracer = get_tracer()
    span = None
    try:
        if tracer:
            span = tracer.start_trace("mcp.client.call", input={"tool": tool_name})
    except Exception:
        span = None
    try:
        client = _mk_client()
        import asyncio

        async def _invoke():
            async with client:
                return await client.call_tool(tool_name, {"payload": params})

        res = asyncio.run(_invoke())
        if isinstance(res, dict):
            try:
                if span:
                    span.set_attribute("ok", True)
                    span.end()
            except Exception:
                pass
            return res
        try:
            data = getattr(res, "data", None)
            if isinstance(data, dict):
                return data
            sc = getattr(res, "structured_content", None)
            if isinstance(sc, dict):
                return sc
        except Exception:
            pass
        out = {"error": "invalid_response", "detail": str(res)}
        try:
            if span:
                span.set_attribute("ok", False)
                span.end()
        except Exception:
            pass
        return out
    except McpUnavailable as ex:
        raise
    except Exception as ex:  # pragma: no cover
        try:
            if span:
                tracer.record_error(span, ex)
        except Exception:
            pass
        raise McpUnavailable(f"OP tool call failed: {ex}")


def discover_fieldmap_via_mcp(project_key: str) -> Optional[Dict[str, Any]]:
    try:
        res = _call_tool("openproject.discover_fieldmap", {"project_key": project_key})
        if "error" in res and res.get("error"):
            log_kv("mcp_error", tool="openproject.discover_fieldmap", project=project_key, error=res.get("error"))
            return None
        return res
    except McpUnavailable as ex:
        log_kv("mcp_unavailable", tool="openproject.discover_fieldmap", project=project_key, reason=str(ex))
        return None


def apply_bp_via_mcp(
    domain: str,
    project_key: str,
    fieldmap: Dict[str, Any],
    bp_plan: Dict[str, Any],
    *,
    max_retries: int,
    backoff_base: float,
    dry_run: bool,
) -> Optional[Tuple[Dict[str, Any], list, list, list, Dict[str, int], Dict[str, float]]]:
    payload = {
        "bundle_domain": domain,
        "project_key": project_key,
        "fieldmap": fieldmap,
        "bp_plan": bp_plan,
        "max_retries": int(max_retries),
        "backoff_base": float(backoff_base),
        "dry_run": bool(dry_run),
    }
    try:
        res = _call_tool("openproject.apply_bp", payload)
        if "error" in res and res.get("error"):
            log_kv("mcp_error", tool="openproject.apply_bp", project=project_key, error=res.get("error"))
            return None
        created = res.get("created") or {}
        warnings = list(res.get("warnings") or [])
        errors = list(res.get("errors") or [])
        stats = dict(res.get("stats") or {})
        timings = dict(res.get("timings") or {})
        updated = list(res.get("updated") or [])
        return created, updated, warnings, errors, stats, timings
    except McpUnavailable as ex:
        log_kv("mcp_unavailable", tool="openproject.apply_bp", project=project_key, reason=str(ex))
        return None


def apply_product_order_via_mcp(
    domain: str,
    project_key: str,
    fieldmap: Dict[str, Any],
    bp_plan: Dict[str, Any],
    *,
    max_retries: int,
    backoff_base: float,
    dry_run: bool,
) -> Optional[Tuple[Dict[str, Any], list, list, list, Dict[str, int], Dict[str, float]]]:
    payload = {
        "bundle_domain": domain,
        "project_key": project_key,
        "fieldmap": fieldmap,
        "bp_plan": bp_plan,
        "max_retries": int(max_retries),
        "backoff_base": float(backoff_base),
        "dry_run": bool(dry_run),
    }
    try:
        res = _call_tool("openproject.apply_product_order", payload)
        if "error" in res and res.get("error"):
            log_kv("mcp_error", tool="openproject.apply_product_order", project=project_key, error=res.get("error"))
            return None
        created = res.get("created") or {}
        warnings = list(res.get("warnings") or [])
        errors = list(res.get("errors") or [])
        stats = dict(res.get("stats") or {})
        timings = dict(res.get("timings") or {})
        updated = list(res.get("updated") or [])
        return created, updated, warnings, errors, stats, timings
    except McpUnavailable as ex:
        log_kv("mcp_unavailable", tool="openproject.apply_product_order", project=project_key, reason=str(ex))
        return None


def apply_plan_via_mcp(plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call the lean apply_openproject_plan tool with a LangGraph-style plan payload."""
    try:
        res = _call_tool("openproject.apply_openproject_plan", plan)
        return res
    except McpUnavailable as ex:
        log_kv("mcp_unavailable", tool="openproject.apply_openproject_plan", reason=str(ex))
        return None
