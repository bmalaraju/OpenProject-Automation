from __future__ import annotations

"""
Router CLI (Phase 5) â€” orchestrates Steps 7â†’8â†’9â†’10.

Behavior
- Parses CLI flags â†’ builds RouterConfig â†’ initializes AgentState (run_id, mode).
- Attempts to run the LangGraph pipeline (if available). If not, falls back to a linear
  offline dryâ€‘run pipeline.
- LLM is explain/summarize only and temperature=0 when enabled; defaults to disabled.

Exit Codes
- 0: success
- 2: invalid RouterConfig/flags
- 3: unreadable inputs (file/registry)
- 4: fatal internal error
"""

import argparse
import os
import sys
from typing import List, Tuple
from pathlib import Path
from dotenv import load_dotenv

import pandas as pd

# Bootstrap env and paths (match other scripts)
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
# Append instead of inserting at front to avoid shadowing third-party modules (e.g., top-level 'mcp')
    sys.path.append(str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)
# Load from project root
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Preload MCP libs early to avoid lazy import hiccups
try:  # noqa: SIM105
    import mcp  # type: ignore
    import mcp.types  # type: ignore
    import fastmcp  # type: ignore
except Exception:
    # Soft-fail: router can still run without MCP
    pass

from wpr_agent.router.types import RouterConfig, AgentState
from wpr_agent.router.utils import gen_run_id, log_kv
from wpr_agent.router.graph import build_router_graph
from wpr_agent.router.tools.registry import load_registry_tool, normalize_domain_tool
from wpr_agent.router.tools.excel import read_excel_normalize_tool, group_domain_bp_tool
from wpr_agent.router.tools.compile import compile_bundle_tool
from wpr_agent.router.tools.validate import validate_bundle_tool, decide_apply_tool
from wpr_agent.router.tools.discovery import discover_fieldmap_tool
from wpr_agent.router.tools.apply import apply_product_order_tool as apply_bp_tool
from wpr_agent.router.tools.report import aggregate_report_tool
from wpr_agent.router.tools.llm import summarize_report_tool
from wpr_agent.router.tools.provision import provision_fields_tool  # stub
from wpr_agent.models import TrackerFieldMap, WprGroup
from wpr_agent.tools.excel_tools import rows_from_df
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:
    def get_tracer():  # type: ignore
        return None


def _bp_group_from_df(bp_id: str, subdf: pd.DataFrame) -> WprGroup:
    rows = rows_from_df(subdf)
    head = rows[0] if rows else None
    return WprGroup(
        bp_id=str(bp_id or ""),
        project_name=(head.project_name if head else str(subdf.iloc[0].get("Project Name", "")) if len(subdf) else ""),
        product=(head.product if head else str(subdf.iloc[0].get("Product", "")) if len(subdf) else ""),
        domain1=(head.domain1 if head else str(subdf.iloc[0].get("Domain", "") or subdf.iloc[0].get("Domain1", "")) if len(subdf) else ""),
        customer=(head.customer if head else str(subdf.iloc[0].get("Customer", "")) if len(subdf) else ""),
        rows=rows,
    )


def parse_args(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Router CLI: orchestrate compileâ†’validateâ†’(apply)â†’report")
    ap.add_argument("--source", choices=["excel", "influx"], default="excel", help="Planning source: excel or influx")
    ap.add_argument("--file", help="Excel file (required when --source excel)")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--since", help="Influx range window (e.g., 12h) when --source influx")
    ap.add_argument("--batch-id", help="Influx batch_id filter when --source influx")
    ap.add_argument("--delta-only", action="store_true", help="When using influx source, apply only changed orders")
    ap.add_argument("--registry", required=True)

    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--online", action="store_true")
    ap.add_argument("--dry-run", action="store_true")

    ap.add_argument("--continue-on-error", action="store_true")
    ap.add_argument("--domains", help="Comma-separated raw domain filter list")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--backoff-base", type=float, default=0.5)

    ap.add_argument("--artifact-dir")
    ap.add_argument("--report")
    ap.add_argument("--summary")
    ap.add_argument("--provision", action="store_true", help="Run provisioning pre-pass per mapped project before compile")
    ap.add_argument("--provision-apply", action="store_true", help="Apply provisioning changes (otherwise preview-only dry-run)")
    ap.add_argument("--provision-profile", help="Provisioning profile JSON (defaults to wpr_agent/profiles/wpr_profile.min.json)")

    ap.add_argument("--llm", action="store_true", help="Enable LLM tools (explain/summarize only; temp=0)")
    ap.add_argument("--domain-concurrency", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--graph-only", action="store_true", help="Fail if LangGraph is unavailable; abort instead of attempting alternatives")
    # Async option (Phase 2)
    ap.add_argument("--async-create-only", action="store_true", help="Use async create-only path for OpenProject apply (experimental)")
    # MCP options
    ap.add_argument("--mcp", choices=["stdio", "http", "https", "ws"], help="Enable MCP client and choose transport")
    ap.add_argument("--mcp-url", help="MCP server URL (for http/https/ws transports)")
    ap.add_argument("--mcp-cmd", help="MCP server command (for stdio transport)")
    ap.add_argument("--mcp-fallback-local-on-error", action="store_true", help="Fallback to local Jira calls when MCP fails")
    ap.add_argument("--mcp-no-fallback", action="store_true", help="Do not fallback to local Jira calls when MCP fails")
    ap.add_argument("--mcp-stub", action="store_true", help="Set stub mode on the MCP server (dev only)")
    return ap.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    # Configure MCP env if requested
    try:
        if args.mcp:
            os.environ["MCP_JIRA_TRANSPORT"] = args.mcp
            if args.mcp_url:
                os.environ["MCP_JIRA_URL"] = args.mcp_url
            if args.mcp_cmd:
                os.environ["MCP_JIRA_CMD"] = args.mcp_cmd
            if args.mcp_no_fallback:
                os.environ["MCP_FALLBACK_LOCAL_ON_ERROR"] = "0"
            elif args.mcp_fallback_local_on_error:
                os.environ["MCP_FALLBACK_LOCAL_ON_ERROR"] = "1"
            if args.mcp_stub:
                os.environ["MCP_JIRA_SERVER_STUB"] = "1"
        # Preload MCP libs when explicit MCP enabled
        if args.mcp:
            try:
                import mcp  # type: ignore
                import fastmcp  # type: ignore
            except Exception:
                pass
    except Exception:
        pass
    # Conditional required: file when source=excel
    if args.source == "excel" and not args.file:
        print("config_error: --file is required when --source excel")
        return 2
    try:
        cfg = RouterConfig(
            source=str(args.source),
            file=str(args.file or ""),
            sheet=str(args.sheet),
            since=str(args.since) if args.since else None,
            batch_id=str(args.batch_id) if args.batch_id else None,
            delta_only=bool(args.delta_only),
            registry_path=args.registry,
            offline=bool(args.offline),
            online=bool(args.online),
            dry_run=bool(args.dry_run),
            continue_on_error=bool(args.continue_on_error),
            domains_filter=[x.strip() for x in (args.domains or "").split(",") if x.strip()],
            max_retries=int(args.max_retries),
            backoff_base=float(args.backoff_base),
            artifact_dir=args.artifact_dir,
            report_path=args.report,
            summary_path=args.summary,
            async_create_only=bool(args.async_create_only),
        )
    except Exception as ex:
        print(f"config_error: {ex}")
        return 2

    run_id = gen_run_id()
    mode = {"offline": cfg.offline, "online": cfg.online, "dry_run": cfg.dry_run}
    state = AgentState(
        run_id=run_id,
        mode=mode,
        config=cfg,
    )

    # LLM gating (explain/summarize only; temp=0)
    llm_enabled = bool(args.llm and os.getenv("OPENAI_API_KEY"))
    state.llm_enabled = llm_enabled
    # Let tools read this flag via env if needed
    if llm_enabled:
        os.environ["ROUTER_LLM_ENABLED"] = "1"
    log_kv("router_start", run_id=run_id, offline=cfg.offline, online=cfg.online, dry_run=cfg.dry_run)
    tracer = get_tracer()
    run_span = None
    try:
        if tracer:
            run_span = tracer.start_trace(
                "router.run",
                input={
                    "source": cfg.source,
                    "since": cfg.since or "",
                    "batch_id": cfg.batch_id or "",
                    "delta_only": bool(cfg.delta_only),
                    "online": bool(cfg.online),
                    "offline": bool(cfg.offline),
                    "dry_run": bool(cfg.dry_run),
                },
                run_id=run_id,
            )
    except Exception:
        run_span = None

    # Pre-flight checks for inputs
    if cfg.offline or cfg.online:
        if not os.path.exists(cfg.registry_path):
            print("input_error: missing --registry path")
            return 3
        if cfg.source == "excel" and not os.path.exists(cfg.file):
            print("input_error: missing --file for excel source")
            return 3

    # Optional provisioning pre-pass (online modes)
    def _provision_prepass() -> None:
        try:
            import json as _json
            from pathlib import Path as _P
            state.registry = load_registry_tool(cfg.registry_path)
            # Determine projects from registry and current Excel domains
            state.excel_df = read_excel_normalize_tool(cfg.file, cfg.sheet)
            grouped = group_domain_bp_tool(state.excel_df)
            seen_projects = set()
            # Include all mapped projects from registry to enforce cross-project consistency
            for _, pk in (state.registry or {}).items():
                if pk:
                    seen_projects.add(pk)
            # Also include any projects observed in the current Excel
            for domain, _ in grouped:
                norm = normalize_domain_tool(domain)
                pk = state.registry.get(norm)
                if pk:
                    seen_projects.add(pk)
            profile_path = args.provision_profile or str(BASE_DIR / "profiles" / "wpr_profile.min.json")
            try:
                prof = _json.loads(_P(profile_path).read_text(encoding="utf-8"))
            except Exception:
                prof = {"fields": []}
            for project_key in sorted(seen_projects):
                prev = provision_fields_tool(project_key, prof, dry_run=(not bool(args.provision_apply)))
                if cfg.artifact_dir:
                    _P(cfg.artifact_dir).mkdir(parents=True, exist_ok=True)
                    suffix = "apply" if args.provision_apply else "preview"
                    outp = _P(cfg.artifact_dir) / f"provision_{suffix}_{project_key}.json"
                    outp.write_text(_json.dumps(prev, indent=2), encoding="utf-8")
                log_kv("provision", project=project_key, created=len(prev.get("created_fields", [])), associated=len(prev.get("associated_fields", [])))
        except Exception as _pex:
            state.warnings.append(f"Provisioning pre-pass failed: {_pex}")

    if cfg.online and bool(args.provision) and cfg.source == "excel":
        _provision_prepass()

    # Try graph path
    app = build_router_graph(domain_concurrency=int(args.domain_concurrency))
    if app is None and bool(args.graph_only):
        print("graph_error: LangGraph unavailable (install langgraph + langgraph-checkpoint-sqlite or remove --graph-only)")
        return 4
    if app is not None and (cfg.offline and cfg.dry_run or cfg.online):
        try:
            # Run the router graph (branches on state.mode)
            result_state = app.invoke(
                state,
                {"configurable": {"thread_id": state.run_id, "checkpoint_ns": "router"}},
            )  # type: ignore[attr-defined]
            # Extract run_report from either attribute or mapping
            run_report = getattr(result_state, "run_report", None)
            if run_report is None and isinstance(result_state, dict):
                run_report = result_state.get("run_report")
            if run_report is None and cfg.report_path and os.path.exists(cfg.report_path):
                # Fallback: read the report JSON written by the graph
                try:
                    import json as _json
                    with open(cfg.report_path, "r", encoding="utf-8") as _fh:
                        run_report = _json.loads(_fh.read())
                except Exception:
                    run_report = None
            if run_report is not None:
                # Optionally write a human-friendly summary using LLM/template
                try:
                    if cfg.summary_path:
                        summary_text = summarize_report_tool(run_report)  # type: ignore[arg-type]
                        if summary_text is None:
                            summary_text = ""
                        with open(cfg.summary_path, "w", encoding="utf-8") as fh:
                            fh.write(summary_text)
                        log_kv("summary_write", path=cfg.summary_path)
                except Exception:
                    pass
                print("router_finished: report_ready")
                try:
                    if run_span and isinstance(run_report, dict):
                        totals = run_report.get("totals", {})
                        for k in ("domains","projects","orders","epics_created","stories_created","issues_updated","warnings","failures"):
                            try:
                                run_span.set_attribute(k, float(totals.get(k, 0)))
                            except Exception:
                                pass
                        run_span.end()
                except Exception:
                    pass
                return 0
            print("router_finished: no_report")
            try:
                if run_span:
                    run_span.end()
            except Exception:
                pass
            return 0
        except Exception as ex:
            log_kv("router_error", error=str(ex))
            if bool(args.graph_only):
                print("graph_error: graph invocation failed and --graph-only set; aborting")
            try:
                if run_span:
                    tracer.record_error(run_span, ex)
                    run_span.end()
            except Exception:
                pass
            return 4
    # Unsupported combo (e.g., offline without dry-run)
    print("router_note: unsupported mode combination for current wiring (offline apply not supported)")
    try:
        if run_span:
            run_span.end()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
