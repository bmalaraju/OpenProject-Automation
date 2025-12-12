from __future__ import annotations

"""
LLM-powered change comment builder for Jira updates.

build_change_comment(deltas, context) -> str
- deltas: list of { key, name, old, new }
- context: { run_id, project_key, issue_type, order_id, instance }

Uses OpenAI client when ROUTER_LLM_ENABLED is set; otherwise falls back to
deterministic, single-paragraph template.
"""

from typing import Any, Dict, List
import os

from wpr_agent.router.llm_config import get_llm_client
from wpr_agent.router.utils import log_kv, redact_error_payload


WHITELIST_KEYS = {
    "summary",
    "duedate",
}


def _sanitize_delta(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "key": str(d.get("key", "")),
        "name": str(d.get("name", d.get("key", ""))),
        "old": "" if d.get("old") is None else str(d.get("old")),
        "new": "" if d.get("new") is None else str(d.get("new")),
    }
    return out


def build_change_comment(deltas: List[Dict[str, Any]], context: Dict[str, Any]) -> str:
    # Redact any potential secrets and clamp
    deltas = [
        _sanitize_delta(x)
        for x in deltas
        if str(x.get("key", "")) not in ("parent",)  # skip linking keys
    ]
    # Optional whitelist for well-known fields; don't filter out custom fields entirely
    pruned: List[Dict[str, Any]] = []
    for d in deltas:
        k = d.get("key", "")
        if k in WHITELIST_KEYS or k.startswith("customfield_"):
            pruned.append(d)
    if not pruned:
        pruned = deltas

    llm_enabled = bool(os.getenv("ROUTER_LLM_ENABLED"))
    llm = get_llm_client(llm_enabled)
    run_id = str(context.get("run_id", ""))
    issue_type = str(context.get("issue_type", ""))
    order_id = str(context.get("order_id", ""))
    instance = str(context.get("instance", ""))
    project_key = str(context.get("project_key", ""))

    # LLM path
    if llm is not None and pruned:
        try:
            system = (
                "You are an assistant that drafts concise, audit-friendly OpenProject change comments. "
                "Summarize the applied field changes in 3-6 lines. Be factual, neutral, and avoid secrets. "
                "Prefer ISO dates, and include run_id."
            )
            user = {
                "run_id": run_id,
                "project_key": project_key,
                "issue_type": issue_type,
                "order_id": order_id,
                "instance": instance,
                "changes": pruned,
            }
            messages = [("system", system), ("human", str(redact_error_payload(user)))]
            res = llm.invoke(messages)  # type: ignore[attr-defined]
            text = getattr(res, "content", "") or str(res)
            lines = [ln for ln in text.splitlines() if ln.strip()][:6]
            text = "\n".join(lines)
            if text:
                log_kv("llm_comment", chars=len(text), used_llm=True)
                return text
        except Exception:
            pass

    # Fallback deterministic comment
    parts = [
        f"WPR Sync {run_id} | {project_key} {issue_type}",
        f"Order: {order_id}{(' #' + instance) if instance else ''}",
        "Changes:",
    ]
    for d in pruned[:6]:
        name = d.get("name") or d.get("key")
        parts.append(f"- {name}: {d.get('old','')} → {d.get('new','')}")
    out = "\n".join(parts)
    log_kv("llm_comment", chars=len(out), used_llm=False)
    return out

