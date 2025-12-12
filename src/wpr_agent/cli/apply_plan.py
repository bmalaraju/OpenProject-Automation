from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import hashlib
import time
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

# Bootstrap env and paths
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wpr_agent.models import PlanBundle, TrackerFieldMap
from wpr_agent.services.provider import make_service  # type: ignore
from wpr_agent.router.utils import log_kv
from wpr_agent.router.tools.llm_comments import build_change_comment
from wpr_agent.state.catalog import Catalog
try:
    from wpr_agent.state.influx_store import InfluxStore  # type: ignore
except Exception:
    InfluxStore = None  # type: ignore


def _ensure_fields_discovered(svc: Any, project_key: str) -> TrackerFieldMap:
    try:
        return svc.discover_fieldmap(project_key)
    except Exception:
        # Fallback to simple discovery
        svc.discover_fields(project_key)
        return JiraFieldMap()


def _parse_order_id_from_epic_summary(summary: str) -> str:
    try:
        if "::" in summary:
            return summary.split("::", 1)[1].strip()
        return summary.split()[0].strip()
    except Exception:
        return summary


def _parse_instance_from_summary(summary: str) -> int:
    try:
        # Support two patterns: '<ORDER_ID>-<n>' and legacy '<ORDER_ID> #<n> | ...'
        if "-" in summary:
            tail = summary.rsplit("-", 1)[-1].strip()
            return int(tail)
        if "#" in summary:
            rest = summary.split("#", 1)[1]
            num = rest.split()[0]
            return int(num)
    except Exception:
        pass
    return 0

# ---------- Fingerprint helpers ----------
def _adf_to_md_for_hash(adf: Dict[str, Any]) -> str:
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
        return json.dumps(adf, separators=(",", ":"))
    except Exception:
        return ""

def _fingerprint_epic(summary: str, description_adf: Dict[str, Any], extra_fields: Dict[str, Any]) -> str:
    subset: Dict[str, Any] = {
        "summary": summary or "",
        "description": _adf_to_md_for_hash(description_adf),
        "custom": {k: extra_fields.get(k) for k in sorted([k for k in (extra_fields or {}).keys() if str(k).startswith("customField")])},
    }
    s = json.dumps(subset, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _fingerprint_story(summary: str, description_adf: Dict[str, Any], due_date: Optional[str], extra_fields: Dict[str, Any]) -> str:
    subset: Dict[str, Any] = {
        "summary": summary or "",
        "description": _adf_to_md_for_hash(description_adf),
        "duedate": due_date or "",
        "custom": {k: extra_fields.get(k) for k in sorted([k for k in (extra_fields or {}).keys() if str(k).startswith("customField")])},
    }
    s = json.dumps(subset, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def apply_bp(
    svc: Any,
    bundle_domain: str,
    project_key: str,
    fieldmap: TrackerFieldMap,
    bp_plan: Dict[str, Any],
    *,
    max_retries: int,
    backoff_base: float,
    dry_run: bool,
    pre_fetched_epics: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], List[str], List[str], Dict[str, int], Dict[str, float]]:
    created: Dict[str, Any] = {"epics": [], "stories": [], "updated": []}
    warnings: List[str] = []
    errors: List[str] = []
    stats: Dict[str, int] = {"retries": 0, "dropped_assignees": 0}
    timings: Dict[str, float] = {"epic_upsert_ms": 0.0, "story_batch_ms": 0.0, "description_update_ms": 0.0}

    epic_ann = bp_plan["epic"]
    epic_plan = epic_ann["plan"]
    epic_summary = epic_plan["summary"]

    epic_key = None
    epic_newly_created = False
    
    def _story_link(svc_obj: Any, key: str) -> str:
        try:
            return svc_obj.story_browse_url("", key) if svc_obj else f"/browse/{key}"
        except Exception:
            return f"/browse/{key}"
    # Choose state store: InfluxDB primary when configured; do not fall back to JSON when Influx is intended
    store: Any
    if InfluxStore is not None and all(os.getenv(k) for k in ("INFLUX_URL","INFLUX_TOKEN","INFLUX_ORG","INFLUX_BUCKET")):
        try:
            store = InfluxStore()
            log_kv("state_store", type="influx")
        except Exception as ex:
            # Enforce InfluxDB as primary: fail fast instead of falling back to JSON
            raise RuntimeError(f"InfluxStore initialization failed: {ex}")
    else:
        # No Influx configuration present: use local JSON catalog
        store = Catalog((Path("artifacts") / "state" / "catalog.json").as_posix())
        log_kv("state_store", type="json_catalog")
    t0 = time.perf_counter()
    if not dry_run:
        try:
            # Resolve Epic: catalog → identity (WPR order ID) → summary
            ex = None
            try:
                order_id_val = str(bp_plan.get("bp_id", "") or "") or _parse_order_id_from_epic_summary(epic_summary)
                
                # Try pre-fetched cache first
                if pre_fetched_epics and order_id_val in pre_fetched_epics:
                    ex = pre_fetched_epics[order_id_val]
                
                if not ex and order_id_val and not os.getenv("IGNORE_INFLUX_IDENTITY"):
                    cat_key = store.resolve_epic(project_key, order_id_val)
                    if cat_key:
                        ex = {"key": cat_key, "fields": {"summary": epic_summary}}
                if not ex and hasattr(svc, "find_epic_by_order_id"):
                    ex = svc.find_epic_by_order_id(project_key, order_id_val, fieldmap)
            except Exception:
                ex = None
            if not ex:
                ex = svc.find_epic_by_summary(project_key, epic_summary)
            if ex:
                epic_key = ex.get("key")
                # Register mapping in catalog
                try:
                    if epic_key and order_id_val:
                        store.register_epic(project_key, order_id_val, epic_key)
                        if isinstance(store, Catalog):
                            store.save()
                except Exception:
                    pass
                planned = svc.build_epic_fields(project_key, epic_summary, epic_plan["description_adf"])
                # merge additional fields from plan (e.g., identity custom fields)
                try:
                    extra = dict(epic_plan.get("fields", {}))
                except Exception:
                    extra = {}
                # Ensure identity (WPR WP order id) is planned when discovered
                try:
                    low = {k.strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
                    ord_fid = low.get("wpr wp order id") or low.get("wpr order id") or low.get("wp order id")
                    ord_val = order_id_val
                    if ord_fid and ord_val and (ord_fid not in extra):
                        extra[ord_fid] = ord_val
                except Exception:
                    pass
                if extra:
                    planned.update(extra)
                # Fingerprint short-circuit
                try:
                    ep_hash = _fingerprint_epic(epic_summary, epic_plan["description_adf"], extra)
                except Exception:
                    ep_hash = None
                last_hash = None
                try:
                    if InfluxStore is not None and isinstance(store, InfluxStore):
                        last_hash = store.get_last_hash(project_key, "Epic", order_id_val, None)
                except Exception:
                    last_hash = None
                print(f"DEBUG: Epic Key={epic_key}, Hash={ep_hash}, LastHash={last_hash}, Force={os.getenv('FORCE_OP_SYNC')}")
                is_hash_match = (ep_hash and last_hash and ep_hash == last_hash and os.getenv("FORCE_OP_SYNC") != "1")
                print(f"DEBUG: IsHashMatch={is_hash_match}")
                
                if is_hash_match:
                    try:
                        if epic_key and order_id_val and InfluxStore is not None and isinstance(store, InfluxStore):
                            store.register_epic(project_key, order_id_val, epic_key, last_hash)
                    except Exception:
                        pass
                    diff = {}
                else:
                    diff = svc.compute_epic_diff(planned, ex.get("fields", {}) or {})
                    # include extra fields diffs explicitly
                    if extra:
                        curf = ex.get("fields", {}) or {}
                        for k, v in extra.items():
                            if curf.get(k) != v:
                                diff[k] = v
                    # Carry forward required status field to satisfy OP validation on updates
                    try:
                        low_cf = {k.strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
                        status_fid = low_cf.get("wpr wp order status")
                        if status_fid and status_fid not in diff:
                            curf = ex.get("fields", {}) or {}
                            cur_status = curf.get(status_fid)
                            if cur_status not in (None, ""):
                                href = None
                                try:
                                    href = (((cur_status.get("_links") or {}).get("customOption") or {}).get("href")) or cur_status.get("href") if isinstance(cur_status, dict) else None
                                except Exception:
                                    href = None
                                if href:
                                    diff[status_fid] = {"href": href}
                                else:
                                    diff[status_fid] = cur_status
                    except Exception:
                        pass
                print(f"DEBUG: Diff Keys={list(diff.keys())}")
                if diff:
                    # Skip description-only updates to avoid OP validation when required CFs are unknown
                    if set(diff.keys()) == {"description"} and os.getenv("FORCE_OP_SYNC") != "1":
                        warnings.append(f"Skip epic description-only update for BP {bp_plan['bp_id']} (no-op)")
                    else:
                        ok, res, r_used, dropped = svc.update_issue_resilient(
                            epic_key, diff, max_retries=max_retries, backoff_base=backoff_base
                        )
                        print(f"DEBUG: Update Result OK={ok}, Res={res}")
                        stats["retries"] += r_used
                        if dropped:
                            stats["dropped_assignees"] += 1
                        if not ok:
                            # Fallback: if the epic key is stale (deleted), create a new Epic now
                            try:
                                is_not_found = False
                                if isinstance(res, dict):
                                    ident = str(res.get("errorIdentifier") or "")
                                    msg = str(res.get("message") or "")
                                    is_not_found = (
                                        "NotFound" in ident or "not be found" in msg or "deleted" in msg
                                    )
                            except Exception:
                                is_not_found = False
                            if is_not_found:
                                ok2, res2, r2, drop2 = svc.create_issue_resilient(
                                    svc.build_epic_fields(project_key, epic_summary, epic_plan["description_adf"]),
                                    max_retries=max_retries,
                                    backoff_base=backoff_base,
                                )
                                stats["retries"] += r2
                                if drop2:
                                    stats["dropped_assignees"] += 1
                                if ok2:
                                    epic_key = res2.get("key") or epic_key
                                    if epic_key:
                                        created["epics"].append(epic_key)
                                        try:
                                            if ep_hash and InfluxStore is not None and isinstance(store, InfluxStore):
                                                store.register_epic(project_key, order_id_val, epic_key, ep_hash)
                                        except Exception:
                                            pass
                                else:
                                    errors.append(f"Epic update failed for BP {bp_plan['bp_id']}: {res}")
                            else:
                                errors.append(f"Epic update failed for BP {bp_plan['bp_id']}: {res}")
                        else:
                            # Record new fingerprint on success
                            try:
                                if ep_hash and InfluxStore is not None and isinstance(store, InfluxStore):
                                    store.register_epic(project_key, order_id_val, epic_key, ep_hash)
                            except Exception:
                                pass
                            # Track Epic update
                            created["updated"].append(epic_key)
                            # Sync Epic status from WPR order status when possible
                            try:
                                svc.sync_epic_status_from_wpr(epic_key, epic_plan.get("fields", {}) or {}, fieldmap)
                            except Exception:
                                pass
                            # Post LLM-authored change comment on Epic
                            try:
                                deltas = []
                                curf = ex.get("fields", {}) or {}
                                for k, v in diff.items():
                                    if k in ("parent",):
                                        continue
                                    deltas.append({"key": k, "old": curf.get(k), "new": v})
                                if deltas:
                                    ctx = {
                                        "run_id": str(uuid.uuid4())[:8],
                                        "project_key": project_key,
                                        "issue_type": "Epic",
                                        "order_id": order_id_val,
                                        "instance": "",
                                    }
                                    body = build_change_comment(deltas, ctx)
                                    if body:
                                        svc.add_comment(epic_key, body)
                            except Exception:
                                pass
                # When an Epic already exists and there is no diff, do nothing
            else:
                # No existing Epic found: create a new one
                fields = svc.build_epic_fields(project_key, epic_summary, epic_plan["description_adf"])
                # merge additional fields from plan
                try:
                    extra = dict(epic_plan.get("fields", {}))
                except Exception:
                    extra = {}
                # Ensure identity (WPR WP order id) is set on create when discovered
                try:
                    low = {k.strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
                    ord_fid = low.get("wpr wp order id") or low.get("wpr order id") or low.get("wp order id")
                    ord_val = order_id_val
                    if ord_fid and ord_val and (ord_fid not in extra):
                        extra[ord_fid] = ord_val
                except Exception:
                    pass
                if extra:
                    fields.update(extra)
                try:
                    ep_hash = _fingerprint_epic(epic_summary, epic_plan["description_adf"], extra)
                except Exception:
                    ep_hash = None
                ok, res, r_used, dropped = svc.create_issue_resilient(
                    fields, max_retries=max_retries, backoff_base=backoff_base
                )
                stats["retries"] += r_used
                if dropped:
                    stats["dropped_assignees"] += 1
                if not ok:
                    errors.append(f"Epic create failed for BP {bp_plan['bp_id']}: {res}")
                else:
                    epic_key = res.get("key")
                    epic_newly_created = True
                    if epic_key:
                        created["epics"].append(epic_key)
                        try:
                            svc.sync_epic_status_from_wpr(epic_key, fields, fieldmap)
                        except Exception:
                            pass
                        try:
                            if epic_key and order_id_val:
                                if ep_hash and InfluxStore is not None and isinstance(store, InfluxStore):
                                    store.register_epic(project_key, order_id_val, epic_key, ep_hash)
                                else:
                                    store.register_epic(project_key, order_id_val, epic_key)
                                if isinstance(store, Catalog):
                                    store.save()
                        except Exception:
                            pass
                    else:
                        errors.append(
                            f"Epic create returned success but no key for BP {bp_plan['bp_id']}; verify Jira gateway response/body"
                        )
        except Exception as ex:
            errors.append(f"Epic upsert error for BP {bp_plan['bp_id']}: {ex}")
    else:
        # Dry-run: simulate Epic create/update decision
        epic_key = "EPIC-DRY"
        
        # Check if Epic would exist (without API call)
        # Use catalog/InfluxStore to determine if this would be create or update
        would_exist = False
        try:
            order_id_val = str(bp_plan.get("bp_id", "") or "") or _parse_order_id_from_epic_summary(epic_summary)
            if order_id_val:
                # Try pre-fetched cache first
                if pre_fetched_epics and order_id_val in pre_fetched_epics:
                    would_exist = True
                # Try catalog/store lookup
                elif not os.getenv("IGNORE_INFLUX_IDENTITY"):
                    try:
                        cat_key = store.resolve_epic(project_key, order_id_val)
                        would_exist = bool(cat_key)
                    except Exception:
                        would_exist = False
        except Exception:
            would_exist = False
        
        # Track appropriately based on whether Epic exists
        if would_exist:
            # Epic exists, would be updated
            created["updated"].append(epic_key)
        else:
            # Epic doesn't exist, would be created
            created["epics"].append(epic_key)
    timings["epic_upsert_ms"] = (time.perf_counter() - t0) * 1000.0

    # Stories
    story_links: List[str] = []
    t1 = time.perf_counter()
    # Bounded concurrency only when the Epic was created in this run (net-new stories)
    try:
        import os as _os
        workers = int(_os.getenv("OP_STORY_WORKERS", "1"))
    except Exception:
        workers = 1
    concurrent_mode = (not dry_run) and bool(epic_key) and bool(epic_newly_created) and workers > 1

    if concurrent_mode:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from threading import Lock
        lock = Lock()
        futures = []
        def _create_story_worker(st_ann: Dict[str, Any]) -> Tuple[Optional[str], List[str], List[str], int, bool]:
            # Returns (story_key, warns, errs, retries_used, dropped_assignee)
            warns: List[str] = []
            errs: List[str] = []
            retries_used = 0
            dropped_assignee = False
            try:
                st = st_ann["plan"]
                st_summary = st["summary"]
                due_date = st.get("fields", {}).get("duedate")
                # Build fields
                st_fields = svc.build_story_fields(project_key, summary=st_summary, description_adf=st["description_adf"], due_date=due_date, assignee_account_id=None, epic_key=epic_key)
                try:
                    st_extra = dict(st.get("fields", {}))
                except Exception:
                    st_extra = {}
                # Identity injection
                try:
                    low = {k.strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
                    order_fid = low.get("wpr wp order id") or low.get("wpr order id") or low.get("wp order id")
                    allow_story_identity = False
                    if order_fid:
                        try:
                            allow_story_identity = svc.has_field_id_on_issuetype(project_key, order_fid, "Story")
                        except Exception:
                            allow_story_identity = False
                    ann_identity = None
                    try:
                        ann_identity = (st_ann.get("identity") or {}).get("value")
                    except Exception:
                        ann_identity = None
                    if order_fid and allow_story_identity and (order_fid not in st_fields) and (order_fid not in st_extra):
                        if ann_identity:
                            st_extra[order_fid] = str(ann_identity)
                        else:
                            _seg = st_summary.split("|")[0].strip() if ("|" in st_summary) else st_summary.split(" - ")[0].strip()
                            if _seg:
                                st_extra[order_fid] = _seg
                except Exception:
                    pass
                if st_extra:
                    st_fields.update(st_extra)
                # Derive identity for mapping
                st_id_value: Optional[str] = None
                try:
                    low = {k.strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
                    for nm in ("wpr wp order id", "wpr order id", "wp order id"):
                        fid = low.get(nm)
                        if fid and (st_extra.get(fid) not in (None, "")):
                            st_id_value = str(st_extra.get(fid))
                            break
                except Exception:
                    st_id_value = None
                if not st_id_value:
                    try:
                        part = st_summary.split("|")[0].strip() if "|" in st_summary else st_summary.split(" - ")[0].strip()
                        st_id_value = part or None
                    except Exception:
                        st_id_value = None
                # Fingerprint
                try:
                    st_hash = _fingerprint_story(st_summary, st["description_adf"], due_date, st_extra)
                except Exception:
                    st_hash = None
                ok, res, r_used, dropped = svc.create_issue_resilient(st_fields, max_retries=max_retries, backoff_base=backoff_base)
                retries_used += r_used
                if dropped:
                    dropped_assignee = True
                if not ok:
                    errs.append(f"Story create failed '{st_summary}': {res}")
                    return None, warns, errs, retries_used, dropped_assignee
                story_key = res.get("key")
                # Register mapping
                try:
                    inst = _parse_instance_from_summary(st_summary)
                    if st_id_value and inst > 0 and story_key:
                        if st_hash and InfluxStore is not None and isinstance(store, InfluxStore):
                            store.register_story(project_key, st_id_value, inst, story_key, st_hash)
                        else:
                            store.register_story(project_key, st_id_value, inst, story_key)
                except Exception:
                    pass
                return story_key, warns, errs, retries_used, dropped_assignee
            except Exception as _ex:
                errs.append(f"Story upsert error worker: {_ex}")
                return None, warns, errs, retries_used, dropped_assignee

        # Submit workers
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for st_ann in bp_plan.get("stories", []):
                futures.append(ex.submit(_create_story_worker, st_ann))
            # Collect
            for fut in as_completed(futures):
                story_key, warns, errs, r_used, dropped = fut.result()
                if story_key:
                    created["stories"].append(story_key)
                    story_links.append(_story_link(svc, story_key))
                if warns:
                    warnings.extend(warns)
                if errs:
                    errors.extend(errs)
                stats["retries"] += r_used
                if dropped:
                    stats["dropped_assignees"] += 1
    else:
        for st_ann in bp_plan.get("stories", []):
            st = st_ann["plan"]
            st_summary = st["summary"]
            due_date = st.get("fields", {}).get("duedate")
            # If we don't have an Epic key (e.g., create failed), skip story creation to preserve linkage policy
            if not dry_run and not epic_key:
                warnings.append(f"Skipping story '{st_summary}' because Epic was not created/resolved for order id '{bp_plan.get('bp_id')}'")
                continue
            if dry_run:
                # Simulate creation
                story_key = f"ST-DRY-{len(created['stories'])+1}"
                created["stories"].append(story_key)
                story_links.append(_story_link(svc, story_key))
                continue

            # Build story fields with epic link
            st_fields = svc.build_story_fields(
                project_key,
                summary=st_summary,
                description_adf=st["description_adf"],
                due_date=due_date,
                assignee_account_id=None,
                epic_key=epic_key,
            )
            # merge additional story fields from plan (e.g., identity custom field)
            try:
                st_extra = dict(st.get("fields", {}))
            except Exception:
                st_extra = {}
            # Pull identity from annotation when available
            ann_identity = None
            try:
                ann_identity = (st_ann.get("identity") or {}).get("value")
            except Exception:
                ann_identity = None
            # Ensure identity (WPR WP order id) is included when discovered and available on Story screens
            try:
                low = {k.strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
                order_fid = low.get("wpr wp order id") or low.get("wpr order id") or low.get("wp order id")
                allow_story_identity = False
                if order_fid:
                    try:
                        allow_story_identity = svc.has_field_id_on_issuetype(project_key, order_fid, "Story")
                    except Exception:
                        allow_story_identity = False
                # If identity field is present on Story and available on screens, inject from annotation (preferred)
                # but do not override when compiler already provided a value in st_fields
                if order_fid and allow_story_identity and (order_fid not in st_fields) and (order_fid not in st_extra):
                    if ann_identity:
                        st_extra[order_fid] = str(ann_identity)
                    else:
                        _seg = st_summary.split("|")[0].strip() if ("|" in st_summary) else st_summary.split(" - ")[0].strip()
                        if _seg:
                            st_extra[order_fid] = _seg
                # If not available on screens, silently skip setting this field (avoid noisy warnings)
            except Exception:
                pass
            if st_extra:
                st_fields.update(st_extra)
            try:
                # Resolve Story by catalog first, then by identity (WPR WP order id)
                st_id_value: Optional[str] = (str(ann_identity) if ann_identity else None)
                try:
                    low = {k.strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
                    for nm in ("wpr wp order id", "wpr order id", "wp order id"):
                        fid = low.get(nm)
                        if fid and (st_extra.get(fid) not in (None, "")):
                            st_id_value = str(st_extra.get(fid))
                            break
                except Exception:
                    st_id_value = None

                def _parse_order_id_from_summary(s: str) -> Optional[str]:
                    try:
                        # Prefer first segment split by '|', else ' - '
                        part = s.split("|")[0].strip() if "|" in s else s.split(" - ")[0].strip()
                        return part or None
                    except Exception:
                        return None

                if not st_id_value:
                    st_id_value = _parse_order_id_from_summary(st_summary)

                ex = None
                skip_lookup = bool(epic_key and epic_newly_created)
                if not skip_lookup:
                    # Try identity store first when available
                    if st_id_value and not os.getenv("IGNORE_INFLUX_IDENTITY"):
                        inst = _parse_instance_from_summary(st_summary)
                        if inst > 0:
                            cat = store.resolve_story(project_key, st_id_value, inst)
                            if cat:
                                ex = {"key": cat, "fields": {"summary": st_summary}}
                    # Service identity-based lookup (if supported)
                    if not ex and st_id_value and hasattr(svc, "find_story_by_order_id"):
                        try:
                            ex = svc.find_story_by_order_id(project_key, st_id_value, epic_key=epic_key, fmap=fieldmap)  # type: ignore[attr-defined]
                        except Exception:
                            ex = None
                        if not ex:
                            try:
                                ex = svc.find_story_by_order_id(project_key, st_id_value, epic_key=None, fmap=fieldmap)  # type: ignore[attr-defined]
                            except Exception:
                                ex = None
                    # Fallback to summary-based match (last resort)
                    if not ex:
                        try:
                            ex = svc.find_story_by_summary(project_key, st_summary)
                        except Exception:
                            ex = None
                if ex:
                    story_key = ex.get("key")
                    # Fingerprint and skip if up-to-date
                    try:
                        st_hash = _fingerprint_story(st_summary, st["description_adf"], due_date, st_extra)
                    except Exception:
                        st_hash = None
                    last_hash = None
                    try:
                        if InfluxStore is not None and isinstance(store, InfluxStore):
                            last_hash = store.get_last_hash(project_key, "Story", st_id_value or "", _parse_instance_from_summary(st_summary))
                    except Exception:
                        last_hash = None
                    if st_hash and last_hash and st_hash == last_hash and os.getenv("FORCE_OP_SYNC") != "1":
                        try:
                            if story_key and st_id_value and InfluxStore is not None and isinstance(store, InfluxStore):
                                inst = _parse_instance_from_summary(st_summary)
                                store.register_story(project_key, st_id_value, inst, story_key, st_hash)
                        except Exception:
                            pass
                        story_links.append(_story_link(svc, story_key))
                        continue
                    # Prepare diff (summary, description, duedate, assignee)
                    diff = svc.compute_story_diff(st_fields, ex.get("fields", {}) or {})
                    # include extra fields diffs explicitly
                    if st_extra:
                        curf = ex.get("fields", {}) or {}
                        for k, v in st_extra.items():
                            if curf.get(k) != v:
                                diff[k] = v
                    # Ensure link: add epic link field when needed
                    if epic_key and svc._epic_link_field:
                        if ex.get("fields", {}).get(svc._epic_link_field) != epic_key:
                            diff[svc._epic_link_field] = epic_key
                    elif epic_key:
                        # Fallback: set parent if epic link is not available
                        diff["parent"] = {"key": epic_key}
                    if diff:
                        ok, res, r_used, dropped = svc.update_issue_resilient(
                            story_key, diff, max_retries=max_retries, backoff_base=backoff_base
                        )
                        stats["retries"] += r_used
                        if dropped:
                            stats["dropped_assignees"] += 1
                        if not ok:
                            # Fallback: if the story key is stale (deleted), create a new Story now
                            try:
                                is_not_found = False
                                if isinstance(res, dict):
                                    ident = str(res.get("errorIdentifier") or "")
                                    msg = str(res.get("message") or "")
                                    is_not_found = (
                                        "NotFound" in ident or "not be found" in msg or "deleted" in msg
                                    )
                            except Exception:
                                is_not_found = False
                            
                            if is_not_found:
                                # Self-healing: Create new story
                                ok2, res2, r2, drop2 = svc.create_issue_resilient(
                                    st_fields, max_retries=max_retries, backoff_base=backoff_base
                                )
                                stats["retries"] += r2
                                if drop2:
                                    stats["dropped_assignees"] += 1
                                if ok2:
                                    story_key = res2.get("key") or story_key
                                    created["updated"].append(story_key) # Log as updated/recovered
                                    # Update mapping in InfluxDB
                                    try:
                                        inst = _parse_instance_from_summary(st_summary)
                                        if story_key and st_id_value and inst > 0:
                                            if st_hash and InfluxStore is not None and isinstance(store, InfluxStore):
                                                store.register_story(project_key, st_id_value, inst, story_key, st_hash)
                                            else:
                                                store.register_story(project_key, st_id_value, inst, story_key)
                                            if isinstance(store, Catalog):
                                                store.save()
                                    except Exception:
                                        pass
                                    # Post LLM-authored change comment on new Story (optional, but consistent)
                                    try:
                                        if diff:
                                            deltas = []
                                            curf = ex.get("fields", {}) or {}
                                            for k, v in diff.items():
                                                if k in ("parent",):
                                                    continue
                                                deltas.append({"key": k, "old": curf.get(k), "new": v})
                                            if deltas:
                                                inst = _parse_instance_from_summary(st_summary)
                                                ctx = {
                                                    "run_id": str(uuid.uuid4())[:8],
                                                    "project_key": project_key,
                                                    "issue_type": "Story",
                                                    "order_id": st_id_value or _parse_order_id_from_summary(st_summary) or "",
                                                    "instance": str(inst if inst > 0 else ""),
                                                }
                                                body = build_change_comment(deltas, ctx)
                                                if body:
                                                    svc.add_comment(story_key, body)
                                    except Exception:
                                        pass
                                else:
                                    errors.append(f"Story update (recovery) failed ({story_key}): {res2}")
                            else:
                                errors.append(f"Story update failed ({story_key}): {res}")
                        else:
                            created["updated"].append(story_key)
                            # Persist fingerprint
                            try:
                                if st_hash and InfluxStore is not None and isinstance(store, InfluxStore) and st_id_value:
                                    inst = _parse_instance_from_summary(st_summary)
                                    store.register_story(project_key, st_id_value, inst, story_key, st_hash)
                            except Exception:
                                pass
                            # Post LLM-authored change comment on Story
                            try:
                                deltas = []
                                curf = ex.get("fields", {}) or {}
                                for k, v in diff.items():
                                    if k in ("parent",):
                                        continue
                                    deltas.append({"key": k, "old": curf.get(k), "new": v})
                                if deltas:
                                    inst = _parse_instance_from_summary(st_summary)
                                    ctx = {
                                        "run_id": str(uuid.uuid4())[:8],
                                        "project_key": project_key,
                                        "issue_type": "Story",
                                        "order_id": st_id_value or _parse_order_id_from_summary(st_summary) or "",
                                        "instance": str(inst if inst > 0 else ""),
                                    }
                                    body = build_change_comment(deltas, ctx)
                                    if body:
                                        svc.add_comment(story_key, body)
                            except Exception:
                                pass
                    story_links.append(_story_link(svc, story_key))
                else:
                    try:
                        st_hash = _fingerprint_story(st_summary, st["description_adf"], due_date, st_extra)
                    except Exception:
                        st_hash = None
                    ok, res, r_used, dropped = svc.create_issue_resilient(
                        st_fields, max_retries=max_retries, backoff_base=backoff_base
                    )
                    stats["retries"] += r_used
                    if dropped:
                        stats["dropped_assignees"] += 1
                    if not ok:
                        errors.append(f"Story create failed '{st_summary}': {res}")
                    else:
                        story_key = res.get("key")
                        created["stories"].append(story_key)
                        story_links.append(_story_link(svc, story_key))
                        try:
                            inst = _parse_instance_from_summary(st_summary)
                            if st_id_value and inst > 0 and story_key:
                                if st_hash and InfluxStore is not None and isinstance(store, InfluxStore):
                                    store.register_story(project_key, st_id_value, inst, story_key, st_hash)
                                else:
                                    store.register_story(project_key, st_id_value, inst, story_key)
                                if isinstance(store, Catalog):
                                    store.save()
                        except Exception:
                            pass
            except Exception as ex:
                errors.append(f"Story upsert error '{st_summary}': {ex}")
    timings["story_batch_ms"] = (time.perf_counter() - t1) * 1000.0

    # Update Epic description with links
    if not dry_run and epic_key and story_links:
        t2 = time.perf_counter()
        try:
            # Reuse original meta; plan already has description_adf meta section
            fields = {"description": {"type": "doc", "version": 1, "content": epic_plan["description_adf"]["content"][:] }}
            # Append a links paragraph block list
            blocks = fields["description"]["content"]
            blocks.append({"type": "paragraph", "content": [{"type": "text", "text": "Work Package Stories:"}]})
            for url in story_links:
                blocks.append({
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "- "},
                        {"type": "text", "text": url, "marks": [{"type": "link", "attrs": {"href": url}}]},
                    ],
                })
            # Carry forward status to satisfy OP validation
            try:
                low_cf = {k.strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
                status_fid = low_cf.get("wpr wp order status")
                if status_fid:
                    cur_wp = svc.client.work_package(epic_key)
                    if isinstance(cur_wp, dict):
                        cur_status = cur_wp.get(status_fid)
                        if cur_status not in (None, ""):
                            href = None
                            try:
                                href = (((cur_status.get("_links") or {}).get("customOption") or {}).get("href")) or cur_status.get("href") if isinstance(cur_status, dict) else None
                            except Exception:
                                href = None
                            if href:
                                fields[status_fid] = {"href": href}
                            else:
                                fields[status_fid] = cur_status
            except Exception:
                pass
            ok, res, r_used, _ = svc.update_issue_resilient(
                epic_key, fields, max_retries=max_retries, backoff_base=backoff_base, allow_assignee_fallback=False
            )
            stats["retries"] += r_used
            if not ok:
                warnings.append(f"Epic description update failed ({epic_key}): {res}")
        except Exception as ex:
            warnings.append(f"Epic description update error ({epic_key}): {ex}")
        timings["description_update_ms"] = (time.perf_counter() - t2) * 1000.0

    return created, warnings, errors, stats, timings


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply PlanBundles to Jira with idempotent upsert and linking.")
    ap.add_argument("--bundles", "-b", default="bundles.json")
    ap.add_argument("--online", action="store_true", help="Discover fieldmaps per project and apply using Jira APIs.")
    ap.add_argument("--dry-run", action="store_true", help="Do not call Jira; print a would-apply summary only.")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--backoff-base", type=float, default=0.5)
    ap.add_argument("--report", required=False, help="Path to write run_report.json (Step 10)")
    ap.add_argument("--summary", required=False, help="Path to write human-readable summary.txt (Step 10)")
    ap.add_argument("--artifact-dir", required=False, help="Directory to write artifacts (overrides --report/--summary paths)")
    args = ap.parse_args()

    # Optional: delegate to in-process OpenProject runner when requested
    try:
        if os.getenv("OPENPROJECT_INPROCESS") == "1" and os.getenv("TRACKER_PROVIDER", "").lower() == "openproject":
            from wpr_agent.cli.apply_with_service import main as op_inprocess_main  # type: ignore
            # Reconstruct argv for the in-process runner
            sys.argv = [
                "apply_with_service.py",
                "--bundles",
                args.bundles,
            ]
            op_inprocess_main()
            return
    except Exception:
        pass

    # Optional: hands-free client_credentials prefetch per execution
    try:
        if os.getenv("OPENPROJECT_CC_AUTO") == "1":
            from wpr_agent.auth.op_cc import fetch_client_credentials_token  # type: ignore
            res = fetch_client_credentials_token()
            if not res.get("ok"):
                # Proceed; service may still have a valid token or use other auth
                pass
    except Exception:
        pass

    p = Path(args.bundles)
    if not p.exists():
        print(json.dumps({"error": f"File not found: {p}"}, indent=2))
        raise SystemExit(1)

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as ex:
        print(json.dumps({"error": f"Failed to read bundles: {ex}"}, indent=2))
        raise SystemExit(1)

    bundles: List[PlanBundle] = [PlanBundle(**bd) for bd in (data.get("bundles") or [])]

    svc = make_service() if args.online else None
    fieldmaps: Dict[str, JiraFieldMap] = {}
    if args.online and svc is not None:
        for b in bundles:
            if b.project_key and b.project_key not in fieldmaps:
                fieldmaps[b.project_key] = _ensure_fields_discovered(svc, b.project_key)

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    run: Dict[str, Any] = {
        "run_id": run_id,
        "version": "1.0",
        "started_at": started_at,
        "mode": {"offline": not args.online, "online": bool(args.online), "dry_run": bool(args.dry_run)},
        "domains": [],
        "totals": {"domains": 0, "projects": 0, "orders": 0, "epics_created": 0, "stories_created": 0, "issues_updated": 0, "warnings": 0, "failures": 0, "retries": 0, "dropped_assignees": 0},
    }
    if args.artifact_dir:
        out_dir = Path(args.artifact_dir) / (datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{run_id[:8]}")
        out_dir.mkdir(parents=True, exist_ok=True)
        run["artifacts_dir"] = str(out_dir)
        report_path = out_dir / "run_report.json"
        summary_path = out_dir / "summary.txt"
    else:
        report_path = Path(args.report) if args.report else None
        summary_path = Path(args.summary) if args.summary else None

    domains_seen: set[tuple[str, str]] = set()
    for b in bundles:
        fmap = fieldmaps.get(b.project_key, JiraFieldMap())
        if args.online and svc is None:
            # Attach a domain block with warning
            run["domains"].append({"domain": b.domain, "project_key": b.project_key, "order_count": len(getattr(b, 'product_plans', []) or []), "epic_count": 0, "story_count": 0, "created_epics": [], "created_stories": [], "updated_issues": [], "skipped_items": [], "warnings": [f"Online mode requested but Jira client not available; skipping {b.project_key}"], "failures": [], "stats": {"retries": 0, "dropped_assignees": 0}, "timings": {}})
            continue
        dom_block = {"domain": b.domain, "project_key": b.project_key, "order_count": len(getattr(b, 'product_plans', []) or []), "epic_count": 0, "story_count": 0, "created_epics": [], "created_stories": [], "updated_issues": [], "skipped_items": [], "warnings": [], "failures": [], "stats": {"retries": 0, "dropped_assignees": 0}, "timings": {"per_order": []}}
        for plan in b.product_plans:
            created, warns, errs, stats, timing = apply_bp(
                svc,  # None in dry-run
                b.domain,
                b.project_key,
                fmap,
                (plan.model_dump() if hasattr(plan, "model_dump") else (plan.dict() if hasattr(plan, "dict") else plan)),
                max_retries=args.max_retries,
                backoff_base=args.backoff_base,
                dry_run=not args.online or args.dry_run,
            )
            dom_block["created_epics"].extend(created.get("epics", []))
            dom_block["created_stories"].extend(created.get("stories", []))
            dom_block["updated_issues"].extend(created.get("updated", []))
            dom_block["warnings"].extend(warns)
            dom_block["failures"].extend(errs)
            dom_block["stats"]["retries"] += stats.get("retries", 0)
            dom_block["stats"]["dropped_assignees"] += stats.get("dropped_assignees", 0)
            dom_block["timings"]["per_order"].append({"order_id": plan.bp_id, **timing})
        dom_block["epic_count"] = len(dom_block["created_epics"])
        dom_block["story_count"] = len(dom_block["created_stories"])
        run["domains"].append(dom_block)
        domains_seen.add((b.domain, b.project_key))

    # Totals and end timestamp
    run["totals"]["domains"] = len(run["domains"])
    run["totals"]["projects"] = len(set((d["project_key"]) for d in run["domains"]))
    run["totals"]["orders"] = sum(d.get("order_count", 0) for d in run["domains"]) 
    run["totals"]["epics_created"] = sum(len(d.get("created_epics", [])) for d in run["domains"]) 
    run["totals"]["stories_created"] = sum(len(d.get("created_stories", [])) for d in run["domains"]) 
    run["totals"]["issues_updated"] = sum(len(d.get("updated_issues", [])) for d in run["domains"]) 
    run["totals"]["warnings"] = sum(len(d.get("warnings", [])) for d in run["domains"]) 
    run["totals"]["failures"] = sum(len(d.get("failures", [])) for d in run["domains"]) 
    run["totals"]["retries"] = sum(d.get("stats", {}).get("retries", 0) for d in run["domains"]) 
    run["totals"]["dropped_assignees"] = sum(d.get("stats", {}).get("dropped_assignees", 0) for d in run["domains"]) 
    run["ended_at"] = datetime.now(timezone.utc).isoformat()

    # Write outputs
    if report_path:
        report_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    if summary_path:
        lines: List[str] = []
        lines.append(f"Run {run['run_id']} started {run['started_at']} ended {run['ended_at']} mode={run['mode']}")
        t = run["totals"]
        lines.append(f"Totals: domains={t['domains']} projects={t['projects']} orders={t['orders']} created(epics={t['epics_created']}, stories={t['stories_created']}) updated={t['issues_updated']} warnings={t['warnings']} failures={t['failures']} retries={t['retries']} dropped_assignees={t['dropped_assignees']}")
        for d in run["domains"]:
            lines.append(f"- {d['domain']} [{d['project_key']}]: orders={d.get('order_count', 0)} created(epics={len(d['created_epics'])}, stories={len(d['created_stories'])}) updated={len(d['updated_issues'])} warnings={len(d['warnings'])} failures={len(d['failures'])}")
        summary_path.write_text("\n".join(lines), encoding="utf-8")

    # Also print to stdout for convenience
    print(json.dumps(run, indent=2))


if __name__ == "__main__":
    main()
