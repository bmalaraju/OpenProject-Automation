from __future__ import annotations

"""
LangGraph orchestration for WPR daily flow:
- optional ingest (Excel -> Influx)
- query latest batch from Influx
- delta detection via checkpoint and source hash
- build LangGraph plan schema
- apply via MCP openproject.apply_openproject_plan
- update checkpoints and hashes
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from wpr_agent.shared import influx_helpers
from wpr_agent.orchestration.wpr_models import WprConfig, WprState, PlanPayload, PlanItem
from wpr_agent.mcp.openproject_client import apply_plan_via_mcp
from wpr_agent.router.utils import log_kv

try:
    from langgraph.graph import StateGraph  # type: ignore
except Exception:
    StateGraph = None  # type: ignore


def _delta_orders(rows: List[Dict[str, Any]], cfg: WprConfig) -> List[Dict[str, Any]]:
    """Select orders whose data changed since last checkpoint using timestamps and source hashes."""
    out: List[Dict[str, Any]] = []
    # group by product/order_id
    from collections import defaultdict

    grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        prod = str(r.get("Product") or r.get("product") or "")
        oid = str(r.get("WP Order ID") or r.get("order_id") or "")
        if not prod or not oid:
            continue
        grouped[(prod, oid)].append(r)

    for (prod, oid), lst in grouped.items():
        try:
            last_data = influx_helpers.get_last_row_time(prod, oid, since=cfg.since, batch_id=cfg.batch_id)
        except Exception:
            last_data = None
        try:
            last_proc = influx_helpers.get_order_checkpoint(cfg.project_key, oid)
        except Exception:
            last_proc = None
        
        # Resolve identity
        try:
            op_id = influx_helpers.resolve_identity(cfg.project_key, oid)
        except Exception:
            op_id = None

        changed_ts = (last_proc is None) or (last_data and str(last_data) > str(last_proc))
        # compute source hash if we have a sub-df; reuse helper via pandas path
        try:
            import pandas as pd  # type: ignore

            df = pd.DataFrame(lst)
            src_hash = influx_helpers.compute_order_src_hash(prod, df)
        except Exception:
            src_hash = None
        try:
            prev_hash = influx_helpers.get_source_hash(cfg.project_key, oid)
        except Exception:
            prev_hash = None
        
        # If we have an ID, it's an update; check hash/ts. If no ID, it's a create.
        # But even for create, we check if we processed it before (idempotency via checkpoint)
        # Actually, if no ID, we MUST create it unless we processed it and failed to save ID?
        # Safe bet: if changed_ts or changed_hash, we process.
        changed_hash = (src_hash is not None) and (src_hash != prev_hash)

        if changed_ts or changed_hash or (not op_id and src_hash):
            exemplar = lst[0] if lst else {}
            exemplar["_product"] = prod
            exemplar["_order_id"] = oid
            exemplar["_src_hash"] = src_hash
            exemplar["_op_id"] = op_id
            out.append(exemplar)
    return out


def _build_plan(cfg: WprConfig, delta_rows: List[Dict[str, Any]]) -> PlanPayload:
    items: List[PlanItem] = []
    for row in delta_rows:
        subject = str(row.get("WP Order ID") or row.get("_order_id") or row.get("order_id") or "")
        desc_lines = [
            f"- WP Name: {row.get('WP Name', '')}",
            f"- WP Quantity: {row.get('WP Quantity', '')}",
            f"- Product: {row.get('Product', '')}",
            f"- Domain: {row.get('Domain', '') or row.get('Domain1', '')}",
            f"- Customer: {row.get('Customer', '')}",
            f"- Status: {row.get('WP Order Status', '')}",
        ]
        description = "\n".join(desc_lines)
        status = row.get("WP Order Status") or None
        custom_fields: Dict[str, Any] = {}
        src_hash = row.get("_src_hash")
        op_id = row.get("_op_id")
        if src_hash:
            custom_fields["customField_src_hash"] = src_hash  # placeholder; mapping handled downstream
        items.append(
            PlanItem(
                id=str(op_id) if op_id else None,
                subject=subject or "WPR Order",
                description=description,
                type="Task",
                status=status if status else None,
                custom_fields=custom_fields,
            )
        )
    return PlanPayload(project_key=cfg.project_key, items=items)


def build_wpr_langgraph(cfg: Optional[WprConfig] = None) -> Optional[Any]:
    if StateGraph is None:
        log_kv("graph_build", available=False)
        return None
    cfg = cfg or WprConfig.from_env_or_kwargs()
    graph = StateGraph(WprState)  # type: ignore[arg-type]

    def ingest_node(state: WprState) -> WprState:
        if state.config.source == "excel" and state.config.file:
            try:
                res = influx_helpers.ingest_excel_to_influx(Path(state.config.file), sheet=state.config.sheet, batch_id=state.config.batch_id)
                state.meta = {"ingest": res} if hasattr(state, "meta") else {"ingest": res}
            except Exception as ex:
                state.errors.append(str(ex))
        return state

    def query_node(state: WprState) -> WprState:
        try:
            df = influx_helpers.query_wpr_rows(since=state.config.since, batch_id=state.config.batch_id)
            rows: List[Dict[str, Any]] = []
            try:
                if df is not None:
                    rows = df.to_dict(orient="records")  # type: ignore[attr-defined]
            except Exception:
                rows = []
            state.rows = rows
        except Exception as ex:
            state.errors.append(str(ex))
        return state

    def delta_node(state: WprState) -> WprState:
        try:
            state.delta_orders = _delta_orders(state.rows, state.config)
        except Exception as ex:
            state.errors.append(str(ex))
        return state

    def plan_node(state: WprState) -> WprState:
        try:
            state.plan = _build_plan(state.config, state.delta_orders)
        except Exception as ex:
            state.errors.append(str(ex))
        return state

    def apply_node(state: WprState) -> WprState:
        if state.plan is None:
            return state
        if state.config.dry_run:
            state.apply_result = {"ok": True, "dry_run": True, "created": [], "updated": []}
            return state
        try:
            res = apply_plan_via_mcp(state.plan.model_dump())
            state.apply_result = res
        except Exception as ex:
            state.apply_result = {"ok": False, "error": str(ex)}
        return state

    def checkpoint_node(state: WprState) -> WprState:
        # Update checkpoints and source hashes for applied orders when succeed
        if not state.apply_result or not state.apply_result.get("ok"):
            return state
        for row in state.delta_orders or []:
            oid = str(row.get("_order_id") or row.get("WP Order ID") or "")
            prod = str(row.get("_product") or row.get("Product") or "")
            if not oid or not prod:
                continue
            try:
                # Register identity if new
                if not row.get("_op_id"):
                    # Find the created ID in apply_result using subject (Order ID)
                    created_list = (state.apply_result or {}).get("created") or []
                    # We assume subject == oid
                    found_id = None
                    for c in created_list:
                        if str(c.get("subject")) == oid:
                            found_id = c.get("id")
                            break
                    
                    if found_id:
                        influx_helpers.register_identity(state.config.project_key, oid, str(found_id))

                if row.get("_src_hash"):
                    influx_helpers.set_source_hash(state.config.project_key, oid, str(row["_src_hash"]))
                
                # Use last row time from this batch
                last_data = influx_helpers.get_last_row_time(prod, oid, since=state.config.since, batch_id=state.config.batch_id)
                if last_data:
                    influx_helpers.set_order_checkpoint(state.config.project_key, oid, str(last_data))
            except Exception:
                continue
        return state

    graph.add_node("ingest", ingest_node)
    graph.add_node("query", query_node)
    graph.add_node("delta", delta_node)
    graph.add_node("plan", plan_node)
    graph.add_node("apply", apply_node)
    graph.add_node("checkpoint", checkpoint_node)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "query")
    graph.add_edge("query", "delta")
    graph.add_edge("delta", "plan")
    graph.add_edge("plan", "apply")
    graph.add_edge("apply", "checkpoint")

    log_kv("graph_build_wpr", available=True)
    return graph.compile()  # type: ignore
