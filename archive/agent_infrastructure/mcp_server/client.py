from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, List
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None

from wpr_agent.router.utils import log_kv
from .config import load, is_enabled

# Best-effort import of mcp to ensure mcp.types is available before fastmcp lazily imports it
try:  # noqa: SIM105
    import mcp as _mcp  # type: ignore  # noqa: F401
except Exception:
    pass


class McpUnavailable(Exception):
    pass


def _mk_client() -> Any:
    cfg = load()
    try:
        # Ensure mcp types module is importable before fastmcp (some builds lazily import it)
        import mcp  # type: ignore  # noqa: F401
        import mcp.types  # type: ignore  # noqa: F401
        import fastmcp  # type: ignore
    except Exception as ex:
        raise McpUnavailable(f"fastmcp not installed: {ex}")

    transport = cfg.get("transport")
    try:
        if transport == "stdio":
            # In-process FastMCP app for local dev
            from wpr_agent.mcp.servers.wpr_server import build_server  # type: ignore
            server_app = build_server()
            client = fastmcp.Client(server_app, timeout=cfg.get("timeout_sec", 30.0))
            return client
        if transport in {"ws", "http", "https"}:
            url = cfg.get("url")
            if not url:
                raise McpUnavailable("MCP_WPR_URL not set for URL transport")
            client = fastmcp.Client(url, timeout=cfg.get("timeout_sec", 30.0))
            return client
    except Exception as ex:
        raise McpUnavailable(f"failed to init fastmcp client: {ex}")
    raise McpUnavailable("unsupported or missing MCP transport configuration")


def call_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not is_enabled():
        raise McpUnavailable("MCP not enabled")
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
                return await client.call_tool(tool_name, params)
        res = asyncio.run(_invoke())
        # fastmcp returns a CallToolResult with .data/.structured_content or a plain dict
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
    except McpUnavailable:
        raise
    except Exception as ex:
        try:
            if span:
                tracer.record_error(span, ex)
        except Exception:
            pass
        raise McpUnavailable(f"tool call failed: {ex}")


def discover_fieldmap(project_key: str) -> Optional[Dict[str, Any]]:
    try:
        res = call_tool("openproject.discover_fieldmap", {"project_key": project_key})
        if "error" in res and res.get("error"):
            log_kv("mcp_error", tool="openproject.discover_fieldmap", project=project_key, error=res.get("error"))
            return None
        return res.get("fieldmap")
    except McpUnavailable as ex:
        log_kv("mcp_unavailable", tool="openproject.discover_fieldmap", project=project_key, reason=str(ex))
        return None


def apply_bp(
    bundle_domain: str,
    project_key: str,
    fieldmap: Dict[str, Any],
    bp_plan: Dict[str, Any],
    *,
    max_retries: int,
    backoff_base: float,
    dry_run: bool,
) -> Optional[Tuple[Dict[str, Any], list, list, list, Dict[str, int], Dict[str, float]]]:
    """
    Adapter to apply a PlanBundle using the lean wpr_server.
    
    1. Flattens PlanBundle to items.
    2. Resolves identities via wpr.resolve_identity.
    3. Calls openproject.apply_openproject_plan.
    4. Registers new identities via wpr.register_identity.
    """
    try:
        items = []
        # Map to track identity info for registration later: subject -> (order_id, issue_type, instance)
        ident_map: Dict[str, Tuple[str, str, int]] = {}

        # Flatten PlanBundle
        product_plans = bp_plan.get("product_plans", [])
        for pp in product_plans:
            # Epic
            epic_ann = pp.get("epic")
            if epic_ann:
                plan = epic_ann.get("plan") or {}
                ident = epic_ann.get("identity") or {}
                order_id = ident.get("value")
                
                item = {
                    "subject": plan.get("summary"),
                    "description": plan.get("description_adf"), # Assuming string/markdown
                    "type": plan.get("issue_type"),
                    "custom_fields": plan.get("fields"),
                }
                
                # Resolve identity
                if order_id:
                    res = call_tool("wpr.resolve_identity", {
                        "project_key": project_key,
                        "order_id": order_id,
                        "issue_type": "Epic"
                    })
                    if res.get("ok") and res.get("issue_key"):
                        item["id"] = res.get("issue_key")
                    else:
                        # Will create new, track for registration
                        ident_map[str(plan.get("summary"))] = (order_id, "Epic", 0)
                
                items.append(item)

            # Stories
            for st_ann in pp.get("stories", []):
                plan = st_ann.get("plan") or {}
                ident = st_ann.get("identity") or {}
                order_id = ident.get("value")
                
                item = {
                    "subject": plan.get("summary"),
                    "description": plan.get("description_adf"),
                    "type": plan.get("issue_type"),
                    "custom_fields": plan.get("fields"),
                }

                # Resolve identity
                if order_id:
                    # Stories might have instance? Assuming 0 for now as per current logic
                    res = call_tool("wpr.resolve_identity", {
                        "project_key": project_key,
                        "order_id": order_id,
                        "issue_type": "Story",
                        "instance": 0
                    })
                    if res.get("ok") and res.get("issue_key"):
                        item["id"] = res.get("issue_key")
                    else:
                        ident_map[str(plan.get("summary"))] = (order_id, "Story", 0)
                
                items.append(item)

        if dry_run:
            return {}, [], [], [], {}, {}

        # Apply
        res = call_tool("openproject.apply_openproject_plan", {
            "project_key": project_key,
            "items": items
        })

        if "error" in res and res.get("error"):
             log_kv("mcp_error", tool="openproject.apply_openproject_plan", project=project_key, error=res.get("error"))
             return None

        created = res.get("created") or []
        updated = res.get("updated") or []
        errors = res.get("errors") or []
        
        # Register identities for created items
        for c in created:
            subj = c.get("subject")
            new_id = c.get("id")
            if subj and new_id and subj in ident_map:
                oid, itype, inst = ident_map[subj]
                call_tool("wpr.register_identity", {
                    "project_key": project_key,
                    "order_id": oid,
                    "issue_key": new_id,
                    "issue_type": itype,
                    "instance": inst
                })

        # Stats/Timings stub
        stats = {"created": len(created), "updated": len(updated), "errors": len(errors)}
        timings: Dict[str, float] = {}

        return created, updated, [], errors, stats, timings

    except McpUnavailable as ex:
        log_kv("mcp_unavailable", tool="openproject.apply_openproject_plan", project=project_key, reason=str(ex))
        return None


def apply_product_order(
    bundle_domain: str,
    project_key: str,
    fieldmap: Dict[str, Any],
    bp_plan: Dict[str, Any],
    *,
    max_retries: int,
    backoff_base: float,
    dry_run: bool,
) -> Optional[Tuple[Dict[str, Any], list, list, list, Dict[str, int], Dict[str, float]]]:
    """Alias for apply_bp."""
    return apply_bp(
        bundle_domain,
        project_key,
        fieldmap,
        bp_plan,
        max_retries=max_retries,
        backoff_base=backoff_base,
        dry_run=dry_run,
    )
