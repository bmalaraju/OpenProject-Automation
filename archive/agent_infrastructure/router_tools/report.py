from __future__ import annotations

"""
Reporting tool for Step 11 Router (Phase 2).

Tool
- aggregate_report_tool(run_id, mode, domain_results, paths) -> (run_report, summary_text?)
  Aggregate per-domain results into RunReport v1 partitions and totals; optionally write JSON and summary.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json

from wpr_agent.router.utils import log_kv, redact_error_payload
from typing import cast


def _sanitize_domains(domains: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Redact sensitive values in per-domain results before serialization.

    Applies `redact_error_payload` to warnings/failures and any nested dict/list structures.
    """
    sanitized: List[Dict[str, Any]] = []
    for d in domains:
        d2: Dict[str, Any] = dict(d)
        for key in ("warnings", "failures"):
            if key in d2:
                val = d2.get(key)
                if isinstance(val, list):
                    d2[key] = [redact_error_payload(x) for x in cast(List[Any], val)]
                else:
                    d2[key] = redact_error_payload(val)
        # Best-effort: redact any nested error/http blocks if present
        for k in list(d2.keys()):
            if isinstance(d2[k], (dict, list, str)):
                d2[k] = redact_error_payload(d2[k])
        sanitized.append(d2)
    return sanitized


def aggregate_report_tool(
    run_id: str,
    mode: Dict[str, bool],
    domain_results: List[Dict[str, Any]],
    *,
    artifact_dir: Optional[str] = None,
    report_path: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Aggregate results into a RunReport v1 and optionally write artifacts.

    Inputs
    - run_id: unique run identifier
    - mode: {offline, online, dry_run}
    - domain_results: list of per-domain dicts (created, updated, warnings, failures, stats, timings)
    - artifact_dir/report_path/summary_path: destinations for outputs (optional)

    Returns
    - (run_report dict, summary_text or None)

    Side effects
    - Writes JSON and text artifacts when paths provided; logs totals
    """
    # Redact before computing totals and writing artifacts
    domains = _sanitize_domains(domain_results)
    totals = {
        "domains": len(domains),
        "projects": len(set(d.get("project_key") for d in domains)),
        "orders": sum((d.get("order_count", 0) or 0) for d in domains),
        "epics_created": sum(len(d.get("created_epics", [])) for d in domains),
        "stories_created": sum(len(d.get("created_stories", [])) for d in domains),
        "issues_updated": sum(len(d.get("updated_issues", [])) for d in domains),
        "warnings": sum(len(d.get("warnings", [])) for d in domains),
        "failures": sum(len(d.get("failures", [])) for d in domains),
        "retries": sum(d.get("stats", {}).get("retries", 0) for d in domains),
        "dropped_assignees": sum(d.get("stats", {}).get("dropped_assignees", 0) for d in domains),
    }
    run_report = {
        "run_id": run_id,
        "version": "1.0",
        "mode": mode,
        "domains": domains,
        "totals": totals,
    }
    log_kv(
        "report_aggregate",
        domains=totals["domains"],
        projects=totals["projects"],
        orders=totals["orders"],
        created_epics=totals["epics_created"],
        created_stories=totals["stories_created"],
        updated=totals["issues_updated"],
        warnings=totals["warnings"],
        failures=totals["failures"],
        retries=totals["retries"],
        dropped=totals["dropped_assignees"],
    )

    # Optional writes
    summary_text: Optional[str] = None
    if artifact_dir:
        out_dir = Path(artifact_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "run_report.json").write_text(json.dumps(run_report, indent=2), encoding="utf-8")
        log_kv("report_write", path=str(out_dir / "run_report.json"))
        if summary_path:
            Path(summary_path).write_text("", encoding="utf-8")
            log_kv("summary_write", path=summary_path)
    else:
        if report_path:
            Path(report_path).write_text(json.dumps(run_report, indent=2), encoding="utf-8")
            log_kv("report_write", path=report_path)
        if summary_path:
            Path(summary_path).write_text("", encoding="utf-8")
            log_kv("summary_write", path=summary_path)

    return run_report, summary_text
