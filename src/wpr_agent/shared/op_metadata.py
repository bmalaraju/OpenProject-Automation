from __future__ import annotations

"""
OpenProject metadata helpers: types, statuses, custom fields.
"""

from typing import Any, Dict

from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2  # type: ignore


def discover_types(project_key: str) -> Dict[str, Any]:
    svc = OpenProjectServiceV2()
    return svc._types_for(project_key)  # type: ignore[attr-defined]


def discover_statuses() -> Dict[str, Any]:
    svc = OpenProjectServiceV2()
    try:
        return svc.client.list_statuses() or {}  # type: ignore[attr-defined]
    except Exception:
        return {}


def discover_custom_fields() -> Dict[str, str]:
    svc = OpenProjectServiceV2()
    try:
        return svc._cf_map()  # type: ignore[attr-defined]
    except Exception:
        return {}


def discover_fieldmap(project_key: str) -> Dict[str, Any]:
    svc = OpenProjectServiceV2()
    fmap = svc.discover_fieldmap(project_key)
    # Normalize to plain dict
    if hasattr(fmap, "model_dump"):
        return fmap.model_dump()  # type: ignore[attr-defined]
    if isinstance(fmap, dict):
        return fmap
    return {}
