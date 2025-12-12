from __future__ import annotations

"""
Status mapping helpers for WPR -> OpenProject.
"""

from typing import Any, Dict, Optional

from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2  # type: ignore


def canonical_wpr_status(name: str) -> str:
    svc = OpenProjectServiceV2()
    return svc._canonical_wpr_status(name)  # type: ignore[attr-defined]


def map_wpr_status_to_openproject(name: str) -> Dict[str, Any]:
    """Return a best-effort OpenProject status suggestion from a WPR status string."""
    svc = OpenProjectServiceV2()
    canon = svc._canonical_wpr_status(name)  # type: ignore[attr-defined]
    # Try to find a matching status in OP by name
    suggestion: Optional[str] = None
    try:
        statuses = (svc.client.list_statuses() or {})  # type: ignore
        low = canon.strip().lower()
        for _k, v in (statuses or {}).items():
            try:
                t = str((v.get("name") or v.get("title") or v.get("id") or "")).strip()
                if t and t.lower() == low:
                    suggestion = t
                    break
            except Exception:
                continue
    except Exception:
        suggestion = None
    return {
        "input": name,
        "canonical": canon,
        "suggested_status": suggestion or canon or "",
        "matched": bool(suggestion),
    }
