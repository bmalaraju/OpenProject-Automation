from __future__ import annotations

"""
LangGraph orchestration (product-based) for the Step 11 Router (InfluxDB 3 / SQL).

Routes by Product→Project, compiles Epic per WPR order id with Stories per
quantity, validates, applies, and aggregates a run report.
"""

from typing import Any, Optional, List, Set, Dict
import os

from wpr_agent.router.types import AgentState
from wpr_agent.router.utils import log_kv
from wpr_agent.router.tools.registry import load_product_registry_tool
from wpr_agent.router.tools.excel import read_excel_normalize_tool, group_product_order_tool
from wpr_agent.router.tools.influx_source import (
    read_influx_df_tool,
    group_product_order_from_df_tool,
)  # type: ignore
from wpr_agent.router.tools.compile_products import compile_product_bundle_tool
from wpr_agent.router.tools.validate import validate_bundle_tool, decide_apply_tool
from wpr_agent.router.tools.discovery import discover_fieldmap_tool
from wpr_agent.router.tools.apply import apply_product_order_tool
from wpr_agent.router.tools.apply_async import apply_product_order_async_tool  # type: ignore
from wpr_agent.router.tools.report import aggregate_report_tool
from wpr_agent.models import TrackerFieldMap
from wpr_agent.state.influx_store import InfluxStore  # type: ignore
try:
    # Optional observability (fail-open)
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None


def build_router_graph(domain_concurrency: int = 1) -> Optional[Any]:
    try:
        from langgraph.graph import StateGraph  # type: ignore
        from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore
    except Exception:
        log_kv("graph_build", available=False)
        return None

    graph = StateGraph(AgentState)  # type: ignore[arg-type]

    def load_registry_node(state: AgentState) -> AgentState:
        state.registry = load_product_registry_tool(state.config.registry_path)
        return state

    def init_influx_node(state: AgentState) -> AgentState:
        # Best-effort ping to ensure Influx is reachable; non-fatal on errors
        try:
            url = os.getenv("INFLUX_URL")
            token = os.getenv("INFLUX_TOKEN")
            org = os.getenv("INFLUX_ORG")
            bucket = os.getenv("INFLUX_BUCKET")
            if url and token and bucket:
                try:
                    import influxdb_client_3  # type: ignore
                    client = influxdb_client_3.InfluxDBClient3(host=url, token=token, org=org, database=bucket)
                    
                    point = {
                        "measurement": "router_run",
                        "tags": {"run_id": str(state.run_id)},
                        "fields": {"event": "start"}
                    }
                    client.write(database=bucket, record=point, write_precision="s")
                    log_kv("influx_init", ok=True)
                except Exception as _iex:
                    log_kv("influx_init", ok=False, error=str(_iex))
        except Exception as _ex:
            log_kv("influx_init", ok=False, error=str(_ex))
        return state

    def read_excel_node(state: AgentState) -> AgentState:
        state.excel_df = read_excel_normalize_tool(state.config.file, state.config.sheet)
        return state

    def read_influx_node(state: AgentState) -> AgentState:
        tracer = get_tracer()
        t = None
        try:
            if tracer:
                t = tracer.start_trace(
                    "router.influx.read",
                    input={"since": state.config.since or "", "batch_id": state.config.batch_id or ""},
                    run_id=state.run_id,
                )
        except Exception:
            t = None
        # Build a DataFrame from Influx input points
        since = state.config.since if (state.config.batch_id is None or state.config.batch_id == "") else None
        try:
            df = read_influx_df_tool(since=since, batch_id=state.config.batch_id)
            try:
                if t is not None and hasattr(df, "shape"):
                    t.set_attribute("rows", int(df.shape[0]))
            except Exception:
                pass
        except Exception as _ex:
            try:
                if tracer:
                    tracer.record_error(t, _ex, where="read_influx_df_tool")
            except Exception:
                pass
            raise
        try:
            from wpr_agent.router.utils import log_kv as _log
            _log("influx_read", rows=(0 if df is None else int(getattr(df, 'shape', [0,0])[0])), since=(since or ""), batch_id=(state.config.batch_id or ""))
        except Exception:
            pass
        state.excel_df = df
        try:
            if t is not None:
                t.end()
        except Exception:
            pass
        return state

    def group_product_order_node(state: AgentState) -> AgentState:
        assert state.excel_df is not None
        state.grouped = group_product_order_tool(state.excel_df)
        return state

    def group_product_order_influx_node(state: AgentState) -> AgentState:
        assert state.excel_df is not None
        state.grouped = group_product_order_from_df_tool(state.excel_df)
        return state

    def filter_delta_orders_node(state: AgentState) -> AgentState:
        # Compute per-project apply mask when delta_only is enabled, using Influx timestamps
        if not state.grouped or not bool(state.config.delta_only):
            return state
        try:
            store = InfluxStore()
            apply_mask: Dict[str, Set[str]] = {}
            for product, order_list in (state.grouped or []):
                project_key = state.registry.get(str(product).strip())
                if not project_key:
                    continue
                
                # OPTIMIZATION: Batch fetch all timestamps for this product/project
                # 1. Get all last processed times for this project
                proc_map = store.get_all_checkpoints(project_key)
                
                # 2. Get all last row times for this product (filtered by batch/since if needed)
                row_map = store.get_all_row_times(
                    str(product or ""), 
                    since=(state.config.since or None), 
                    batch_id=(state.config.batch_id or None)
                )

                for order_id, _sub in order_list:
                    oid = str(order_id or "").strip()
                    if not oid:
                        continue
                    
                    # O(1) Lookup
                    last_data = row_map.get(oid)
                    if not last_data:
                        continue
                        
                    last_proc = proc_map.get(oid)
                    
                    # Compare
                    if (last_proc is None) or (str(last_data) > str(last_proc)):
                        apply_mask.setdefault(project_key, set()).add(oid)
            state.apply_mask = apply_mask
            changed = sum(len(v) for v in apply_mask.values())
            log_kv("delta_filter", projects=len(apply_mask), total_changed=int(changed))
        except Exception as _ex:
            log_kv("delta_filter_error", error=str(_ex))
        return state

    def compile_validate_node(state: AgentState) -> AgentState:
        tracer = get_tracer()
        parent = None
        try:
            if tracer:
                parent = tracer.start_trace("router.compile_validate", run_id=state.run_id)
        except Exception:
            parent = None
        if not state.grouped:
            return state
        for product, order_list in (state.grouped or []):
            project_key = state.registry.get(str(product).strip())
            if not project_key:
                state.warnings.append(f"No project mapping for product '{product}'. Skipping.")
                continue
            bundle = compile_product_bundle_tool(str(product or ""), project_key, TrackerFieldMap(), order_list)
            state.bundles.append(bundle)
            report = validate_bundle_tool(bundle, TrackerFieldMap())
            state.validation_reports[project_key] = report
            try:
                if tracer and parent:
                    sp = tracer.start_span(
                        "router.compile_validate.domain",
                        parent=parent,
                        domain=str(product or ""),
                        project_key=project_key,
                        orders=len(bundle.product_plans) if bundle else 0,
                        errors=len(report.errors or []),
                        warnings=len(report.warnings or []),
                    )
                    if sp:
                        sp.end()
            except Exception:
                pass
        try:
            if parent:
                parent.end()
        except Exception:
            pass
        return state

    def discover_compile_validate_apply_apply_dedupe(order_list, seen_set):
        out = []
        dups = 0
        for oid, sub in (order_list or []):
            sid = str(oid or "").strip()
            if not sid:
                continue
            if sid in seen_set:
                dups += 1
                continue
            seen_set.add(sid)
            out.append((sid, sub))
        return out, dups

    def discover_compile_validate_apply_node(state: AgentState) -> AgentState:
        tracer = get_tracer()
        parent = None
        try:
            if tracer:
                parent = tracer.start_trace("router.apply", run_id=state.run_id)
        except Exception:
            parent = None
        if not state.grouped:
            return state
        try:
            from wpr_agent.services.provider import make_service
            svc = make_service()
        except Exception:
            svc = None  # type: ignore
        if state.mode.get("dry_run", False):
            svc = None

        # Track duplicates across products that map to the same project
        seen_orders_by_project: Dict[str, Set[str]] = {}
        for product, order_list in (state.grouped or []):
            project_key = state.registry.get(str(product).strip())
            if not project_key:
                state.warnings.append(f"No project mapping for product '{product}'. Skipping.")
                continue
            fmap = discover_fieldmap_tool(project_key)
            state.fieldmaps[project_key] = fmap
            seen = seen_orders_by_project.setdefault(project_key, set())
            deduped_orders, dup_count = discover_compile_validate_apply_apply_dedupe(order_list, seen)
            if dup_count:
                state.warnings.append(f"Dedup: skipped {dup_count} duplicate orders for project {project_key} across products")
            
            # OPTIMIZATION: Filter *before* compile if delta-only
            if bool(state.config.delta_only) and isinstance(state.apply_mask, dict):
                mask = state.apply_mask.get(project_key)
                if mask is not None:
                    # Keep only orders that are in the mask
                    deduped_orders = [
                        (oid, sub) for (oid, sub) in deduped_orders 
                        if oid in mask
                    ]
            
            bundle = compile_product_bundle_tool(str(product or ""), project_key, fmap, deduped_orders)
            state.bundles.append(bundle)
            report = validate_bundle_tool(bundle, fmap)
            state.validation_reports[project_key] = report
            allowed, blocked = decide_apply_tool(report, state.config.continue_on_error)
            # Intersect validation-allowed set with delta mask when provided
            try:
                if bool(state.config.delta_only) and isinstance(state.apply_mask, dict):
                    mask = state.apply_mask.get(project_key)
                    if mask:
                        allowed = allowed.intersection(mask)
            except Exception:
                pass
            state.apply_mask[project_key] = allowed

            created_epics: List[str] = []
            created_stories: List[str] = []
            updated_issues: List[str] = []
            warnings: List[str] = list(report.warnings)
            failures: List[str] = list(report.errors)
            stats = {"retries": 0, "dropped_assignees": 0}
            timings = {"per_order": []}

            if bundle and bundle.product_plans:
                start_idx = int(state.apply_progress.get(project_key, 0))
                for i, plan in enumerate(bundle.product_plans):
                    if i < start_idx or plan.bp_id not in allowed:
                        continue
                    # Choose async create-only path for OpenProject when requested
                    use_async = bool(state.config.async_create_only) and (os.getenv("TRACKER_PROVIDER", "jira").strip().lower() == "openproject")
                    if use_async:
                        created, warns, errs, st_stats, tms = apply_product_order_async_tool(
                            str(product or ""), project_key, fmap, plan,
                            max_retries=state.config.max_retries,
                            backoff_base=state.config.backoff_base,
                            dry_run=state.mode.get("dry_run", False),
                        )
                        updated = []
                    else:
                        created, updated, warns, errs, st_stats, tms = apply_product_order_tool(
                            svc, str(product or ""), project_key, fmap, plan,
                            max_retries=state.config.max_retries,
                            backoff_base=state.config.backoff_base,
                            dry_run=state.mode.get("dry_run", False),
                        )
                    created_epics.extend(list(created.get("epics", [])))
                    created_stories.extend(list(created.get("stories", [])))
                    updated_issues.extend(list(updated or []))
                    warnings.extend(list(warns or []))
                    failures.extend(list(errs or []))
                    stats["retries"] += int(st_stats.get("retries", 0))
                    stats["dropped_assignees"] += int(st_stats.get("dropped_assignees", 0))
                    per = {"order_id": plan.bp_id, **{k: float(v) for k, v in (tms or {}).items()}}
                    timings["per_order"].append(per)
                    state.apply_progress[project_key] = i + 1
                    # Persist last processed timestamp for this order when apply succeeded (online, not dry-run)
                    try:
                        if svc is not None and not state.mode.get("dry_run", False) and not errs:
                            store = InfluxStore()
                            last_data = store.get_last_row_time(str(product or ""), str(getattr(plan, 'bp_id', '')), since=(state.config.since or None), batch_id=(state.config.batch_id or None))
                            if last_data:
                                store.set_last_processed_time(project_key, str(getattr(plan, 'bp_id', '')), last_data)
                    except Exception:
                        pass

            dom_res = {
                "domain": product,
                "project_key": project_key,
                "order_count": len(bundle.product_plans) if bundle else 0,
                "created_epics": created_epics,
                "created_stories": created_stories,
                "updated_issues": updated_issues,
                "warnings": warnings,
                "failures": failures,
                "stats": stats,
                "timings": timings,
            }
            state.domain_results.append(dom_res)
            try:
                if tracer and parent:
                    sp = tracer.start_span(
                        "router.apply.domain",
                        parent=parent,
                        domain=str(product or ""),
                        project_key=project_key,
                        orders=len(bundle.product_plans) if bundle else 0,
                        created_epics=len(created_epics),
                        created_stories=len(created_stories),
                        updated=len(updated_issues),
                        failures=len(failures),
                    )
                    if sp:
                        sp.end()
            except Exception:
                pass
        try:
            if parent:
                parent.end()
        except Exception:
            pass
        return state

    def _route_after_group(state: AgentState) -> str:
        return "online" if state.mode.get("online", False) else "offline"

    def _route_source(state: AgentState) -> str:
        s = (state.config.source or "excel").strip().lower()
        return "influx" if s == "influx" else "excel"

    def aggregate_report_node(state: AgentState) -> AgentState:
        run_report, _ = aggregate_report_tool(
            state.run_id,
            state.mode,
            state.domain_results,
            artifact_dir=state.config.artifact_dir,
            report_path=state.config.report_path,
            summary_path=state.config.summary_path,
        )
        state.run_report = run_report
        return state

    def write_run_metrics_node(state: AgentState) -> AgentState:
        # Write basic summary metrics to Influx (non-fatal on errors)
        try:
            url = os.getenv("INFLUX_URL")
            token = os.getenv("INFLUX_TOKEN")
            org = os.getenv("INFLUX_ORG")
            bucket = os.getenv("INFLUX_BUCKET")
            if url and token and bucket and state.run_report:
                import influxdb_client_3  # type: ignore
                client = influxdb_client_3.InfluxDBClient3(host=url, token=token, org=org, database=bucket)
                
                totals = state.run_report.get("totals", {}) if isinstance(state.run_report, dict) else {}
                
                fields = {}
                for k in ("domains", "projects", "orders", "epics_created", "stories_created", "issues_updated", "warnings", "failures", "retries", "dropped_assignees"):
                    try:
                        v = float(totals.get(k, 0))
                        fields[k] = v
                    except Exception:
                        continue
                
                point = {
                    "measurement": "router_run",
                    "tags": {"run_id": str(state.run_id)},
                    "fields": fields
                }
                client.write(database=bucket, record=point, write_precision="s")
                log_kv("influx_metrics", ok=True)
        except Exception as _ex:
            log_kv("influx_metrics", ok=False, error=str(_ex))
        return state

    # Wiring
    try:
        graph.add_node("load_registry", load_registry_node)
        graph.add_node("read_excel", read_excel_node)
        graph.add_node("read_influx", read_influx_node)
        graph.add_node("init_influx", init_influx_node)
        graph.add_node("group_product_order", group_product_order_node)
        graph.add_node("group_product_order_influx", group_product_order_influx_node)
        graph.add_node("filter_delta_orders", filter_delta_orders_node)
        graph.add_node("compile_validate", compile_validate_node)
        graph.add_node("discover_compile_validate_apply", discover_compile_validate_apply_node)
        graph.add_node("aggregate_report", aggregate_report_node)

        graph.set_entry_point("load_registry")
        graph.add_edge("load_registry", "init_influx")
        # Choose source path
        graph.add_conditional_edges(
            "init_influx",
            _route_source,
            {"excel": "read_excel", "influx": "read_influx"},
        )
        # Excel path
        graph.add_edge("read_excel", "group_product_order")
        graph.add_conditional_edges(
            "group_product_order",
            _route_after_group,
            {"offline": "compile_validate", "online": "discover_compile_validate_apply"},
        )
        # Influx path
        graph.add_edge("read_influx", "group_product_order_influx")
        graph.add_edge("group_product_order_influx", "filter_delta_orders")
        graph.add_conditional_edges(
            "filter_delta_orders",
            _route_after_group,
            {"offline": "compile_validate", "online": "discover_compile_validate_apply"},
        )
        graph.add_edge("compile_validate", "aggregate_report")
        graph.add_edge("discover_compile_validate_apply", "aggregate_report")
        graph.add_node("write_run_metrics", write_run_metrics_node)
        graph.add_edge("aggregate_report", "write_run_metrics")
    except Exception:
        log_kv("graph_wiring_error", ok=False)
        return None

    log_kv("graph_build", available=True, domain_concurrency=domain_concurrency)
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore
        cp = SqliteSaver.from_conn_string("router_checkpoints.sqlite")  # type: ignore
        # Newer langgraph-checkpoint returns a context manager; older returns a saver
        if hasattr(cp, "get_next_version"):
            app = graph.compile(checkpointer=cp)  # type: ignore
        else:
            # Fallback: compile without checkpointer to avoid runtime errors
            app = graph.compile()  # type: ignore
    except Exception:
        app = graph.compile()  # type: ignore
    return app
