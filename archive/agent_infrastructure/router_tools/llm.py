from __future__ import annotations

"""
LLM tool stubs for Step 11 Router (Phase 2).

Tools (optional; temperature=0 policy)
- interpret_error_tool(error_ctx) -> dict
  Explain validation/apply errors with classification and actions; fallback to deterministic explainer when LLM unavailable.

- summarize_report_tool(run_report) -> str
  Summarize the run in 8–12 lines; fallback to template when LLM unavailable.

Note: This module provides bounded stubs to be replaced/extended in Phase 3.
"""

from typing import Any, Dict

from wpr_agent.router.utils import log_kv, redact_error_payload
from wpr_agent.router.llm_config import get_llm_client
import os


def interpret_error_tool(error_ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Explain an error context with a safe, non‑mutative recommendation.

    Inputs
    - error_ctx: dict containing route/step/project/domain/http/error/taxonomy/request_hint (redacted before use)

    Returns
    - dict: { classification, why, actions: [ { title, step, detail } ] }

    Side effects
    - Logs the classification and whether LLM was used (here: fallback only)
    """
    ctx = redact_error_payload(error_ctx)
    # Try LLM if enabled
    llm_enabled = bool(os.getenv("ROUTER_LLM_ENABLED"))
    llm = get_llm_client(llm_enabled)
    if llm is not None:
        try:
            system = (
                "You are an OpenProject operations assistant. Explain errors and recommend safe, non-mutative actions "
                "aligned with our pipeline. Allowed: retry/backoff (Step 6), drop assignee once, provisioning checklist (Step 12), "
                "fix Excel mapping. Forbidden: changing mapped values (IDs, names, dates, summaries). Output JSON only."
            )
            user = {
                "route": ctx.get("route"),
                "step": ctx.get("step"),
                "project_key": ctx.get("project_key"),
                "domain": ctx.get("domain"),
                "http": ctx.get("http"),
                "error": ctx.get("error"),
                "taxonomy": ctx.get("taxonomy"),
                "request_hint": ctx.get("request_hint"),
                "task": "Classify; explain why; list 2–3 actions (JSON).",
            }
            messages = [
                ("system", system),
                ("human", str(user)),
            ]
            res = llm.invoke(messages)  # type: ignore[attr-defined]
            text = getattr(res, "content", "") or str(res)
            # Best-effort JSON extraction
            import json

            data = json.loads(text)
            if not isinstance(data, dict) or "classification" not in data or "actions" not in data:
                raise ValueError("invalid LLM JSON shape")
            log_kv("llm_interpret", classification=data.get("classification"), used_llm=True)
            return data
        except Exception:
            pass
    # Fallback, rule-based minimal explainer
    status = str(((ctx.get("http") or {}).get("status") or "")).lower()
    classification = "unknown"
    why = "insufficient context"
    actions = []
    if status == "429":
        classification = "rate_limited"
        why = "Too many requests"
        actions = [
            {"title": "Retry with backoff", "step": 6, "detail": "Increase backoff_base and retry once window passes."}
        ]
    log_kv("llm_interpret", classification=classification, used_llm=False)
    return {"classification": classification, "why": why, "actions": actions}


def summarize_report_tool(run_report: Dict[str, Any]) -> str:
    """Produce a short, human‑readable summary from RunReport (template fallback).

    Inputs
    - run_report: dict with totals and domains partition per Step 10

    Returns
    - str: 8–12 lines summary (best‑effort template)
    """
    llm_enabled = bool(os.getenv("ROUTER_LLM_ENABLED"))
    llm = get_llm_client(llm_enabled)
    if llm is not None:
        try:
            system = (
                "You are a release reporter. Summarize the OpenProject run factually and concisely (8–12 lines). "
                "Include overall totals, per-domain/project bullets, top warnings/failures, and next steps. Do not expose secrets."
            )
            user = {k: run_report.get(k) for k in ("run_id", "mode", "totals", "domains")}
            messages = [("system", system), ("human", str(user))]
            res = llm.invoke(messages)  # type: ignore[attr-defined]
            text = getattr(res, "content", "") or str(res)
            # constrain to 12 lines max
            lines = [ln for ln in text.splitlines() if ln.strip()][:12]
            text = "\n".join(lines)
            log_kv("llm_summary", chars=len(text), used_llm=True)
            return text
        except Exception:
            pass
    # Fallback template
    t = run_report.get("totals", {})
    lines = [
        f"Run {run_report.get('run_id','')} | dry_run={run_report.get('mode',{}).get('dry_run')} | domains={t.get('domains',0)} projects={t.get('projects',0)}",
        f"Created epics={t.get('epics_created',0)} stories={t.get('stories_created',0)} | updated={t.get('issues_updated',0)}",
        f"Warnings={t.get('warnings',0)} Failures={t.get('failures',0)} Retries={t.get('retries',0)} DroppedAssignees={t.get('dropped_assignees',0)}",
    ]
    for d in (run_report.get("domains") or [])[:5]:
        oc = d.get('order_count', 0)
        lines.append(
            f"- {d.get('domain','')} [{d.get('project_key','')}]: orders={oc} created(epics={len(d.get('created_epics',[]))},stories={len(d.get('created_stories',[]))}) updated={len(d.get('updated_issues',[]))}"
        )
    text = "\n".join(lines)
    log_kv("llm_summary", chars=len(text), used_llm=False)
    return text
