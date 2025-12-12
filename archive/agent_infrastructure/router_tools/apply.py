from __future__ import annotations

"""
Apply tool for Step 11 Router (Phase 2).

Tool
- apply_product_order_tool(svc, domain, project_key, fieldmap, bp_plan, opts)
  Upsert Epic/Stories for one product order with resilience; sets identity fields when discovered; ensures linking
  (Epic Link/parent); collects stats and timings. In dry-run, simulates creation keys.

Compatibility
- apply_bp_tool(...) remains as a thin alias to apply_product_order_tool(...)
"""

from typing import Any, Dict, Tuple, List

from wpr_agent.models import TrackerFieldMap
from wpr_agent.router.utils import log_kv
from wpr_agent.mcp.config import is_enabled as mcp_enabled, load as load_mcp_cfg
from wpr_agent.mcp.openproject_client import apply_product_order_via_mcp as op_apply_product_order_via_mcp


def apply_product_order_tool(
    svc: Any,
    domain: str,
    project_key: str,
    fieldmap: TrackerFieldMap,
    bp_plan: Any,
    *,
    max_retries: int,
    backoff_base: float,
    dry_run: bool,

) -> Tuple[Dict[str, Any], List[str], List[str], List[str], Dict[str, int], Dict[str, float]]:
    """Apply a single product-order plan with resilience and return aggregates.

    Inputs
    - svc: OpenProjectServiceV2 instance (or None for dry-run)
    - domain: Domain label
    - project_key: Project key
    - fieldmap: TrackerFieldMap (not used directly here; present for signature symmetry)
    - bp_plan: ProductPlan (from PlanBundle)
    - max_retries/backoff_base: resilience parameters
    - dry_run: when True, simulate keys and skip network calls

    Returns
    - (created, updated, warnings, errors, stats, timings) as dicts

    Side effects
    - Prints a concise log with created/updated counts and resilience stats
    """
    # Try MCP first when enabled
    if mcp_enabled():
        try:
            mres = op_apply_product_order_via_mcp(
                domain,
                project_key,
                fieldmap,
                bp_plan,
                max_retries=max_retries,
                backoff_base=backoff_base,
                dry_run=dry_run,
            )
        except Exception as _mex:
            mres = None
        if mres is not None:
            created, updated_keys, warns, errs, stats, timings = mres
            created_count = len(created.get("stories", [])) + len(created.get("epics", []))
            log_kv(
                "apply_product_order",
                domain=domain,
                project=project_key,
                bp_id=getattr(bp_plan, "bp_id", None),
                created=created_count,
                updated=len(updated_keys),
                retries=stats.get("retries", 0),
                dropped_assignees=stats.get("dropped_assignees", 0),
            )
            return created, updated_keys, list(warns), list(errs), stats, timings
        # If MCP failed and fallback is allowed, continue to local path
        mcp_cfg = load_mcp_cfg()
        if not bool(mcp_cfg.get("fallback_local_on_error", True)):
            # Hard fail shape: no creations; surface error via warnings
            return {"epics": [], "stories": [], "updated": []}, [], ["MCP apply failed"], [], {"retries": 0, "dropped_assignees": 0}, {"epic_upsert_ms": 0.0, "story_batch_ms": 0.0, "description_update_ms": 0.0}

    # Import local apply when MCP is disabled or failed and fallback allowed
    from wpr_agent.cli.apply_plan import apply_bp  # type: ignore

    # Convert Pydantic model to dict if needed
    if hasattr(bp_plan, "model_dump"):
        payload = bp_plan.model_dump()  # type: ignore[attr-defined]
    elif hasattr(bp_plan, "dict"):
        payload = bp_plan.dict()
    else:
        payload = bp_plan
    created, warns, errs, stats, timings = apply_bp(
        svc,
        bundle_domain=domain,
        project_key=project_key,
        fieldmap=fieldmap,
        bp_plan=payload,
        max_retries=max_retries,
        backoff_base=backoff_base,
        dry_run=dry_run,
    )

    created_count = len(created.get("stories", [])) + len(created.get("epics", []))
    updated_keys: List[str] = list(created.get("updated", []))
    log_kv(
        "apply_product_order",
        domain=domain,
        project=project_key,
        bp_id=getattr(bp_plan, "bp_id", None),
        created=created_count,
        updated=len(updated_keys),
        retries=stats.get("retries", 0),
        dropped_assignees=stats.get("dropped_assignees", 0),
    )
    # Normalize return shape to match plan: created, updated, warnings, errors, stats, timings
    return created, updated_keys, list(warns), list(errs), stats, timings


# Backward-compat alias
def apply_bp_tool(
    svc: Any,
    domain: str,
    project_key: str,
    fieldmap: TrackerFieldMap,
    bp_plan: Any,
    *,
    max_retries: int,
    backoff_base: float,
    dry_run: bool,
):
    return apply_product_order_tool(
        svc,
        domain,
        project_key,
        fieldmap,
        bp_plan,
        max_retries=max_retries,
        backoff_base=backoff_base,
        dry_run=dry_run,
    )
