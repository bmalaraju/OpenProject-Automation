from __future__ import annotations

"""
Async apply tool (Phase 2 wiring): create Epic and Stories via OpenProject async service.

Scope: create-only path (no searches/diffs). Intended for first-run bulk create with
bounded concurrency. Falls back to sync identity writes to Influx when available.
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Tuple, Optional

from wpr_agent.services.openproject_service_async import OpenProjectServiceV2Async  # type: ignore
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None


def _adf_to_markdown(adf: Dict[str, Any]) -> str:
    try:
        content = (adf or {}).get("content") or []
        if isinstance(content, list) and content:
            first = content[0] or {}
            para = (first.get("content") or [])
            if isinstance(para, list) and para and isinstance(para[0], dict):
                text = str(para[0].get("text") or "")
                return text
    except Exception:
        pass
    try:
        import json as _json
        return _json.dumps(adf)
    except Exception:
        return ""


async def _apply_async_create_only(
    domain: str,
    project_key: str,
    fieldmap: Any,
    bp_plan: Any,
    *,
    max_retries: int,
    backoff_base: float,
    dry_run: bool,
) -> Tuple[Dict[str, Any], List[str], List[str], Dict[str, int], Dict[str, float]]:
    created: Dict[str, Any] = {"epics": [], "stories": [], "updated": []}
    warnings: List[str] = []
    errors: List[str] = []
    stats: Dict[str, int] = {"retries": 0, "dropped_assignees": 0}
    timings: Dict[str, float] = {"epic_upsert_ms": 0.0, "story_batch_ms": 0.0, "description_update_ms": 0.0}

    # Normalize plan to dict
    if hasattr(bp_plan, "model_dump"):
        plan = bp_plan.model_dump()
    elif hasattr(bp_plan, "dict"):
        plan = bp_plan.dict()
    else:
        plan = bp_plan

    svc = OpenProjectServiceV2Async()

    epic_ann = plan.get("epic") or {}
    epic_plan = epic_ann.get("plan") or {}
    epic_summary = str(epic_plan.get("summary") or "")
    epic_desc_adf = epic_plan.get("description_adf") or {}
    epic_desc_md = _adf_to_markdown(epic_desc_adf)

    epic_key: Optional[str] = None
    t0 = time.perf_counter()
    if dry_run:
        epic_key = "EPIC-ASYNC-DRY"
    else:
        # Merge additional custom fields compiled for Epic (e.g., WPR fields)
        epic_extra = {}
        try:
            epic_extra = dict(epic_plan.get("fields", {}) or {})
        except Exception:
            epic_extra = {}
        ep_fields = {"summary": epic_summary, "description": epic_desc_md}
        if epic_extra:
            ep_fields.update(epic_extra)
        tracer = get_tracer()
        span_ep = None
        try:
            if tracer:
                span_ep = tracer.start_trace("op.create.epic.async", input={"project_key": project_key, "summary": epic_summary})
        except Exception:
            span_ep = None
        ok, res = await svc.create_issue(project_key, "Epic", ep_fields)
        try:
            if span_ep:
                span_ep.set_attribute("ok", bool(ok))
                span_ep.end()
        except Exception:
            pass
        if not ok:
            errors.append(f"Epic create failed (async) for order '{plan.get('bp_id') or plan.get('id') or ''}': {res}")
        else:
            ek = str(res.get("key") or res.get("id") or "").strip()
            if ek:
                epic_key = ek
                created["epics"].append(ek)
                # Best-effort Epic status transition based on WPR status (custom field)
                try:
                    ok_status = await svc.sync_epic_status_from_wpr(ek, project_key, ep_fields)
                    if not ok_status:
                        warnings.append(
                            f"Epic status transition skipped or failed for order id {plan.get('bp_id') or plan.get('id') or ''}"
                        )
                except Exception:
                    pass
    timings["epic_upsert_ms"] = (time.perf_counter() - t0) * 1000.0

    # Stories
    t1 = time.perf_counter()
    if epic_key:
        # Concurrency control
        try:
            workers = int(os.getenv("OP_STORY_WORKERS", "6"))
        except Exception:
            workers = 6
        sem = asyncio.Semaphore(max(1, workers))
        tasks: List[asyncio.Task] = []

        async def _create_one(st_ann: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
            st = st_ann.get("plan") or {}
            st_summary = str(st.get("summary") or "")
            st_desc = _adf_to_markdown(st.get("description_adf") or {})
            fields = {"summary": st_summary, "description": st_desc, "parent": {"key": epic_key}}
            # Carry over custom fields (e.g., status, identity, dates) compiled on the plan
            try:
                st_extra = dict(st.get("fields", {}) or {})
            except Exception:
                st_extra = {}
            if st_extra:
                fields.update(st_extra)
            await sem.acquire()
            try:
                if dry_run:
                    return True, f"ST-ASYNC-DRY-{st_summary}", {}
                # Basic retry for transient update conflicts (409)
                attempts = 0
                tracer = get_tracer()
                span_st = None
                try:
                    if tracer:
                        span_st = tracer.start_trace("op.create.story.async", input={"project_key": project_key, "summary": st_summary})
                except Exception:
                    span_st = None
                while True:
                    ok, res = await svc.create_issue(project_key, "Story", fields)
                    key = str((res or {}).get("key") or (res or {}).get("id") or "").strip()
                    if ok:
                        try:
                            if span_st:
                                span_st.set_attribute("attempts", attempts + 1)
                                span_st.set_attribute("ok", True)
                                span_st.end()
                        except Exception:
                            pass
                        return ok, key, res
                    err_ident = ""
                    try:
                        err_ident = str((res or {}).get("errorIdentifier") or "")
                    except Exception:
                        err_ident = ""
                    if "UpdateConflict" in err_ident and attempts < 3:
                        attempts += 1
                        await asyncio.sleep(0.3 * attempts)
                        continue
                    try:
                        if span_st:
                            span_st.set_attribute("attempts", attempts + 1)
                            span_st.set_attribute("ok", False)
                            span_st.set_attribute("errorIdentifier", err_ident)
                            span_st.end()
                    except Exception:
                        pass
                    return ok, key, res
            finally:
                try:
                    sem.release()
                except Exception:
                    pass

        for st_ann in plan.get("stories", []) or []:
            tasks.append(asyncio.create_task(_create_one(st_ann)))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    errors.append(f"Story create error (async): {r}")
                    continue
                ok, key, body = r
                if ok and key:
                    created["stories"].append(key)
                else:
                    errors.append(f"Story create failed (async): {body}")
    else:
        for st_ann in plan.get("stories", []) or []:
            st = st_ann.get("plan") or {}
            warnings.append(
                f"Skipping story '{st.get('summary')}' because Epic was not created (async) for order id '{plan.get('bp_id') or plan.get('id') or ''}'"
            )
    timings["story_batch_ms"] = (time.perf_counter() - t1) * 1000.0
    return created, warnings, errors, stats, timings


def apply_product_order_async_tool(
    domain: str,
    project_key: str,
    fieldmap: Any,
    bp_plan: Any,
    *,
    max_retries: int,
    backoff_base: float,
    dry_run: bool,
) -> Tuple[Dict[str, Any], List[str], List[str], Dict[str, int], Dict[str, float]]:
    """Sync wrapper that runs the async create-only path for one order.

    Returns
    - (created, warnings, errors, stats, timings)
    """
    return asyncio.run(
        _apply_async_create_only(
            domain,
            project_key,
            fieldmap,
            bp_plan,
            max_retries=max_retries,
            backoff_base=backoff_base,
            dry_run=dry_run,
        )
    )
