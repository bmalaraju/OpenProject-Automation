from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json
import os
import time
import random

from wpr_agent.models import TrackerFieldMap
from wpr_agent.clients.openproject_client import OpenProjectClient
from wpr_agent.router.utils import log_kv
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None


class OpenProjectServiceV2:
    """OpenProject-backed service implementing the same public surface as JiraServiceV2.

    Methods used by the pipeline:
    - check_access(project_key)
    - discover_fields(project_key) / discover_fieldmap(project_key)
    - build_epic_fields(...), build_story_fields(...)
    - create_issue_resilient(fields, max_retries, backoff_base, allow_assignee_fallback)
    - update_issue_resilient(issue_key, fields, ...)
    - find_epic_by_summary(project_key, summary)
    - find_story_by_summary(project_key, summary)
    - compute_epic_diff / compute_story_diff
    - add_comment(issue_key, body)
    - story_browse_url(project_base_url, key)
    """

    def __init__(self) -> None:
        self.client = OpenProjectClient()
        self._project_cache: Dict[str, Dict[str, Any]] = {}
        self._types_cache: Dict[str, Dict[str, Any]] = {}  # project_id -> name->type
        self._custom_fields: Optional[Dict[str, str]] = None  # name(lower) -> attribute key
        self._epic_link_field: Optional[str] = None
        self._epic_name_field: Optional[str] = None
        # Cached schemas and options
        self._form_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._options_title_href: Optional[Dict[str, str]] = None

    # ---------- Utils ----------
    def _project_obj(self, project_key: str) -> Optional[Dict[str, Any]]:
        if project_key in self._project_cache:
            return self._project_cache[project_key]
        obj = self.client.resolve_project(project_key)
        if obj:
            self._project_cache[project_key] = obj
        return obj

    def _project_id(self, project_key: str) -> Optional[str]:
        obj = self._project_obj(project_key)
        try:
            return str(obj.get("id")).strip() if obj else None
        except Exception:
            return None

    def _types_for(self, project_key: str) -> Dict[str, Any]:
        pid = self._project_id(project_key)
        if not pid:
            return {}
        if pid in self._types_cache:
            return self._types_cache[pid]
        m = self.client.list_types_for_project(pid)
        self._types_cache[pid] = m
        return m

    def _type_id(self, project_key: str, name: str) -> Optional[str]:
        m = self._types_for(project_key)
        key = (name or "").strip().lower()
        # Map common synonyms to OpenProject type names
        alias = {
            "story": "user story",
            "userstory": "user story",
            "epic": "epic",
            "task": "task",
        }.get(key, key)
        return str((m.get(alias) or {}).get("id") or "").strip() or None

    def _get_form_schema(self, project_id: str, type_id: str) -> Dict[str, Any]:
        key = (str(project_id), str(type_id))
        if key in self._form_cache:
            return self._form_cache[key]
        status, data = self.client.work_package_form(project_id, type_id)
        if status == 200 and isinstance(data, dict):
            self._form_cache[key] = data
            return data
        return {}

    def _get_global_options_map(self) -> Dict[str, str]:
        if self._options_title_href is not None:
            return self._options_title_href
        items = self.client.list_custom_options()
        m: Dict[str, str] = {}
        for opt in (items or []):
            try:
                title = str(opt.get("title") or opt.get("name") or "").strip()
                href = ((opt.get("_links") or {}).get("self") or {}).get("href")
                if not href and opt.get("id"):
                    href = f"/api/v3/custom_options/{opt.get('id')}"
                if title and href:
                    m[title.lower()] = href
            except Exception:
                continue
        self._options_title_href = m
        return m

    def _cf_map(self) -> Dict[str, str]:
        # Populate when uninitialized or when previously fetched empty
        if self._custom_fields is None or not self._custom_fields:
            cf = self.client.list_custom_fields() or {}
            if not cf:
                try:
                    import json, os
                    p = os.getenv("OP_FIELD_ID_OVERRIDES_PATH") or os.path.join("wpr_agent", "config", "op_field_id_overrides.json")
                    with open(p, "r", encoding="utf-8") as fh:
                        data = json.load(fh) or {}
                    cf = {str(k).strip().lower(): str(v) for k, v in (data.items() if isinstance(data, dict) else [])}
                except Exception:
                    cf = {}
            self._custom_fields = cf
        return self._custom_fields or {}

    def _adf_to_markdown(self, adf: Dict[str, Any]) -> str:
        # Our ADF descriptions are single paragraph with "- key: value" lines; extract safely
        try:
            content = (adf or {}).get("content") or []
            if isinstance(content, list) and content:
                first = content[0] or {}
                para = (first.get("content") or [])
                if isinstance(para, list) and para and isinstance(para[0], dict):
                    text = str(para[0].get("text") or "")
                    return text[:20000]
        except Exception:
            pass
        # Fallback: stringify
        try:
            return json.dumps(adf)[:20000]
        except Exception:
            return ""

    def _sleep_backoff(self, attempt: int, base_seconds: float, jitter: float = 0.25) -> None:
        delay = base_seconds * (2 ** max(0, attempt - 1))
        if jitter:
            delay += random.uniform(0, jitter)
        time.sleep(min(delay, 30.0))

    # ---------- Public API ----------
    def check_access(self, project_key: str) -> Dict[str, Any]:
        try:
            obj = self._project_obj(project_key)
            return {"ok": bool(obj), "status": 200 if obj else 404}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    def discover_fields(self, project_key: str) -> Dict[str, Optional[str]]:
        # For OP, Epic Link/Epic Name custom fields are not used
        self._custom_fields = self.client.list_custom_fields()
        self._epic_link_field = None
        self._epic_name_field = None
        return {"epic_link_field": None, "epic_name_field": None}

    def discover_fieldmap(self, project_key: str) -> TrackerFieldMap:
        # Use type discovery and custom field listing; Start date support present for Story
        self.discover_fields(project_key)
        # Build required_fields_by_type via a light heuristic (OP forms API is richer; keep minimal to avoid coupling)
        # For now, leave as empty and rely on apply-time validation.
        cf = self._cf_map()
        return TrackerFieldMap(
            epic_link_field_id=self._epic_link_field,
            epic_name_field_id=self._epic_name_field,
            start_date_supported=True,
            required_fields_by_type={},
            discovered_custom_fields=cf,
        )

    def build_epic_fields(self, project_key: str, summary: str, description_adf: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "project": {"key": project_key},
            "issuetype": {"name": "Epic"},
            "summary": summary or "",
            "description": description_adf,
        }

    def build_story_fields(
        self,
        project_key: str,
        *,
        summary: str,
        description_adf: Dict[str, Any],
        due_date: Optional[str],
        assignee_account_id: Optional[str],
        epic_key: Optional[str],
    ) -> Dict[str, Any]:
        fields: Dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": {"name": "Story"},
            "summary": summary or "",
            "description": description_adf,
        }
        if due_date:
            fields["duedate"] = due_date
        if epic_key:
            fields["parent"] = {"key": str(epic_key)}
        # Assignee resolution optional; ignored by default
        return fields

    def _to_payload(self, project_key: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        pid = self._project_id(project_key)
        t_name = ((fields.get("issuetype") or {}).get("name") or "").strip()
        tid = self._type_id(project_key, t_name) if t_name else None
        payload: Dict[str, Any] = {}
        if "summary" in fields:
            payload["subject"] = fields.get("summary") or ""
        if "description" in fields:
            desc_md = self._adf_to_markdown(fields.get("description") or {})
            payload["description"] = {"raw": desc_md, "format": "markdown"}
        if pid:
            payload.setdefault("_links", {}).setdefault("project", {"href": f"/api/v3/projects/{pid}"})
        if tid:
            payload.setdefault("_links", {}).setdefault("type", {"href": f"/api/v3/types/{tid}"})
        # Dates
        if "duedate" in fields:
            payload["dueDate"] = fields.get("duedate")
        # Parent link
        parent = (fields.get("parent") or {}).get("key") if isinstance(fields.get("parent"), dict) else None
        if parent:
            payload.setdefault("_links", {}).setdefault("parent", {"href": f"/api/v3/work_packages/{parent}"})
        # Custom fields: map list-type values (e.g., WPR WP Order Status) to option links when possible
        cf_map = self._cf_map()
        # Identify status field id if present
        status_fid = None
        try:
            status_fid = cf_map.get("wpr wp order status")
        except Exception:
            status_fid = None
        for k, v in list(fields.items()):
            if isinstance(k, str) and k.startswith("customField"):
                # Skip blank custom field values to avoid server-side 'can't be blank' violations
                try:
                    if (isinstance(v, str) and v.strip() == "") or v is None:
                        continue
                except Exception:
                    pass
                # Try to coerce string to option link for list fields (status)
                if k == status_fid:
                    print(f"DEBUG [{project_key}]: Processing status field: k={k}, v={v}, type={type(v)}, pid={pid}, tid={tid}")
                if (k == status_fid) and isinstance(v, str) and pid and tid:
                    print(f"DEBUG [{project_key}]: Status field condition MET - attempting href conversion")
                    href = None
                    try:
                        # Fetch cached form schema and match allowed values by title
                        schema_data = self._get_form_schema(pid, tid)
                        schema = schema_data.get("schema") or {}
                        fmeta = schema.get(k) or {}
                        allowed = None
                        try:
                            allowed = ((fmeta.get("_links") or {}).get("allowedValues"))
                        except Exception:
                            allowed = None
                        if not allowed:
                            allowed = fmeta.get("allowedValues")
                        print(f"DEBUG [{project_key}]: Schema allowed values count: {len(allowed) if allowed else 0}")
                        if isinstance(allowed, list):
                            sval = v.strip().lower()
                            norm_map = {
                                "pending acknowledgement": "Pending Acknowledgement",
                                "pending acknowledgment": "Pending Acknowledgement",
                                "acknowledge": "Acknowledged",
                                "acknowledged": "Acknowledged",
                                "pending approval": "Pending Approval",
                                "approved": "Approved",
                                "objected": "Objected",
                                "rejected": "Rejected",
                                "cancelled": "Cancelled",
                                "canceled": "Cancelled",
                                "waiting for order submission": "Waiting for order submission",
                            }
                            canon = norm_map.get(sval, v)
                            for opt in allowed:
                                try:
                                    title = str(opt.get("title") or opt.get("name") or "")
                                    href_candidate = ((opt.get("_links") or {}).get("self") or {}).get("href") or opt.get("href")
                                    if href_candidate and title and title.strip().lower() == canon.strip().lower():
                                        href = href_candidate
                                        break
                                except Exception:
                                    continue
                    except Exception:
                        href = None
                    if href:
                        payload[k] = {"href": href}
                    else:
                        # Fallback: search global custom options and match by title
                        try:
                            options_map = self._get_global_options_map()
                            sval = (v or "").strip()
                            # Apply canonical mapping
                            norm_map = {
                                "pending acknowledgement": "Pending Acknowledgement",
                                "pending acknowledgment": "Pending Acknowledgement",
                                "acknowledge": "Acknowledged",
                                "acknowledged": "Acknowledged",
                                "pending approval": "Pending Approval",
                                "approved": "Approved",
                                "objected": "Objected",
                                "rejected": "Rejected",
                                "cancelled": "Cancelled",
                                "canceled": "Cancelled",
                                "waiting for order submission": "Waiting for order submission",
                            }
                            canon = norm_map.get(sval.lower(), sval)
                            href_candidate = options_map.get(canon.strip().lower())
                            if href_candidate:
                                href = href_candidate
                            if href:
                                payload[k] = {"href": href}
                            else:
                                # Final fallback: overrides from config
                                try:
                                    import json, os
                                    p = os.getenv("OP_CUSTOM_OPTION_OVERRIDES_PATH") or os.path.join("wpr_agent", "config", "op_custom_option_overrides.json")
                                    with open(p, "r", encoding="utf-8") as fh:
                                        data = json.load(fh) or {}
                                    # Prefer field-id based mapping
                                    m = data.get(k) or {}
                                    if not m:
                                        # Also allow name-based mapping under display name key
                                        m = data.get("WPR WP Order Status") or {}
                                    href_candidate = m.get(canon) or m.get(v)
                                    if href_candidate:
                                        payload[k] = {"href": href_candidate}
                                    else:
                                        payload[k] = v
                                except Exception:
                                    payload[k] = v
                        except Exception:
                            payload[k] = v
                # Pass-through all custom fields (moved outside status_fid block)
                else:
                    payload[k] = v
        # DEBUG: Print payload for inspection
        try:
            print(f"DEBUG: Full Payload for {project_key}: {json.dumps(payload)}")
        except Exception:
            print(f"DEBUG: Full Payload for {project_key}: (json error) {payload}")
        
        if "customField10" in payload:
             print(f"DEBUG: Payload for {project_key} (Status Field): {payload.get('customField10')}")
        return payload

    def create_issue_resilient(
        self,
        fields: Dict[str, Any],
        *,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        allow_assignee_fallback: bool = True,
    ) -> Tuple[bool, Dict[str, Any], int, bool]:
        retries_used = 0
        dropped_assignee = False
        project_key = ((fields.get("project") or {}).get("key") or "")
        attempt = 0
        tracer = get_tracer()
        span = None
        try:
            if tracer:
                span = tracer.start_trace("op.create", input={"project_key": project_key})
        except Exception:
            span = None
        while True:
            attempt += 1
            payload = self._to_payload(project_key, fields)
            status, body = self.client.create_work_package(payload)
            if status in (200, 201):
                key = str(body.get("id") or "").strip()
                if key:
                    try:
                        if span:
                            span.set_attribute("ok", True)
                            span.set_attribute("attempts", attempt)
                            span.end()
                    except Exception:
                        pass
                    return True, {"key": key}, retries_used, dropped_assignee
                # Fallback to parse from _links/self
                try:
                    href = ((body.get("_links") or {}).get("self") or {}).get("href")
                    if isinstance(href, str) and href.rstrip("/").split("/")[-1].isdigit():
                        try:
                            if span:
                                span.set_attribute("ok", True)
                                span.set_attribute("attempts", attempt)
                                span.end()
                        except Exception:
                            pass
                        return True, {"key": href.rstrip("/").split("/")[-1]}, retries_used, dropped_assignee
                except Exception:
                    pass
                try:
                    if span:
                        span.set_attribute("ok", True)
                        span.set_attribute("attempts", attempt)
                        span.end()
                except Exception:
                    pass
                return True, body, retries_used, dropped_assignee
            if status == 429 or (500 <= status < 600):
                retries_used += 1
                if attempt > max_retries:
                    try:
                        if span:
                            span.set_attribute("ok", False)
                            span.set_attribute("attempts", attempt)
                            span.set_attribute("status", int(status))
                            span.end()
                    except Exception:
                        pass
                    return False, body, retries_used, dropped_assignee
                ra = None
                try:
                    ra = float((body.get("Retry-After") or 0))
                except Exception:
                    ra = None
                if ra:
                    time.sleep(min(ra, 60.0))
                else:
                    self._sleep_backoff(attempt, backoff_base)
                continue
            # Non-retriable
            try:
                if span:
                    span.set_attribute("ok", False)
                    span.set_attribute("attempts", attempt)
                    span.set_attribute("status", int(status))
                    span.end()
            except Exception:
                pass
            return False, body, retries_used, dropped_assignee

    def update_issue_resilient(
        self,
        issue_key: str,
        fields: Dict[str, Any],
        *,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        allow_assignee_fallback: bool = True,
    ) -> Tuple[bool, Dict[str, Any], int, bool]:
        retries_used = 0
        dropped_assignee = False
        attempt = 0
        # Retrieve current WP for lockVersion and to carry forward required custom fields
        wp = self.client.work_package(issue_key)
        lock_version = int((wp or {}).get("lockVersion") or 0)
        
        # Extract project info from work package for _to_payload context
        # Use project ID directly to avoid identifier case sensitivity issues
        project_key_for_payload = ""
        project_id_direct = None
        try:
            if wp:
                # Get project ID directly from work package
                project_href = (((wp.get("_links") or {}).get("project") or {}).get("href"))
                if project_href and isinstance(project_href, str):
                    # Extract project ID from href like "/api/v3/projects/14"
                    project_id_direct = project_href.rstrip("/").split("/")[-1]
                    if project_id_direct:
                        # For _to_payload, we'll pass the ID directly as the key
                        # _to_payload will use it with _project_id which accepts both ID and identifier
                        project_key_for_payload = project_id_direct
        except Exception:
            # Fallback: empty string (will cause pid/tid to be None in _to_payload)
            project_key_for_payload = ""
        
        # Carry forward existing customField* values to avoid server-side 'can't be blank' on required fields
        try:
            if isinstance(wp, dict):
                carry: Dict[str, Any] = {}
                for k, v in wp.items():
                    if isinstance(k, str) and k.startswith("customField") and (v is not None and v != ""):
                        carry[k] = v
                if carry:
                    # Do not overwrite diffs supplied by caller
                    for ck, cv in carry.items():
                        if ck not in fields:
                            fields[ck] = cv
                
                # Extract type name from work package for _to_payload context
                # This ensures tid can be resolved even when diff doesn't include issuetype
                if "issuetype" not in fields:
                    try:
                        type_obj = (((wp.get("_links") or {}).get("type") or {}))
                        type_name = type_obj.get("title") or ""
                        if type_name:
                            fields["issuetype"] = {"name": type_name}
                    except Exception:
                        pass
                
                # Normalize status field to OP link form when possible
                try:
                    cf = self._cf_map()
                    status_fid = cf.get("wpr wp order status")
                except Exception:
                    status_fid = None
                if status_fid and isinstance(fields.get(status_fid), dict):
                    try:
                        cur = fields.get(status_fid) or {}
                        href = (((cur.get("_links") or {}).get("customOption") or {}).get("href")) or cur.get("href")
                        if href:
                            fields[status_fid] = {"href": href}
                    except Exception:
                        pass
        except Exception:
            pass
        tracer = get_tracer()
        span_u = None
        try:
            if tracer:
                span_u = tracer.start_trace("op.update", input={"project_key": project_key_for_payload, "issue": str(issue_key)})
        except Exception:
            span_u = None
        while True:
            attempt += 1
            payload = self._to_payload(project_key_for_payload, fields)
            if lock_version is not None:
                payload["lockVersion"] = lock_version
            status, body = self.client.update_work_package(issue_key, payload)
            if status in (200, 204):
                try:
                    if span_u:
                        span_u.set_attribute("ok", True)
                        span_u.set_attribute("attempts", attempt)
                        span_u.end()
                except Exception:
                    pass
                return True, {"ok": True}, retries_used, dropped_assignee
            if status == 409:
                # Version conflict: refresh and retry
                retries_used += 1
                if attempt > max_retries:
                    try:
                        if span_u:
                            span_u.set_attribute("ok", False)
                            span_u.set_attribute("attempts", attempt)
                            span_u.set_attribute("status", int(status))
                            span_u.end()
                    except Exception:
                        pass
                    return False, body, retries_used, dropped_assignee
                wp = self.client.work_package(issue_key)
                lock_version = int((wp or {}).get("lockVersion") or 0)
                continue
            if status == 429 or (500 <= status < 600):
                retries_used += 1
                if attempt > max_retries:
                    try:
                        if span_u:
                            span_u.set_attribute("ok", False)
                            span_u.set_attribute("attempts", attempt)
                            span_u.set_attribute("status", int(status))
                            span_u.end()
                    except Exception:
                        pass
                    return False, body, retries_used, dropped_assignee
                self._sleep_backoff(attempt, backoff_base)
                continue
            try:
                if span_u:
                    span_u.set_attribute("ok", False)
                    span_u.set_attribute("attempts", attempt)
                    span_u.set_attribute("status", int(status))
                    span_u.end()
            except Exception:
                pass
            return False, body, retries_used, dropped_assignee

    # ---------- Find & diff ----------
    def _map_current_fields(self, wp: Dict[str, Any]) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}
        try:
            fields["summary"] = str(wp.get("subject") or "")
            fields["duedate"] = str(wp.get("dueDate") or "")
            # custom fields
            for k, v in wp.items():
                if isinstance(k, str) and k.startswith("customField"):
                    fields[k] = v
        except Exception:
            pass
        return fields

    def find_epic_by_summary(self, project_key: str, summary: str) -> Optional[Dict[str, Any]]:
        pid = self._project_id(project_key)
        tid = self._type_id(project_key, "Epic")
        if not (pid and tid and summary):
            return None
        # exact subject match first
        filters = [
            {"project": {"operator": "=", "values": [pid]}},
            {"type": {"operator": "=", "values": [tid]}},
            {"subject": {"operator": "=", "values": [summary]}},
        ]
        hits = self.client.search_work_packages(filters, page_size=10)
        hit = hits[0] if hits else None
        if not hit:
            # contains fallback
            filters[-1] = {"subject": {"operator": "contains", "values": [summary]}}
            hits = self.client.search_work_packages(filters, page_size=10)
            hit = hits[0] if hits else None
        if not hit:
            return None
        # fetch full
        try:
            href = ((hit.get("_links") or {}).get("self") or {}).get("href")
            wid = href.rstrip("/").split("/")[-1] if isinstance(href, str) else None
            wp = self.client.work_package(wid) if wid else None
            if not wp:
                return None
            return {"key": str(wp.get("id")), "fields": self._map_current_fields(wp)}
        except Exception:
            return None

    def find_story_by_summary(self, project_key: str, summary: str) -> Optional[Dict[str, Any]]:
        pid = self._project_id(project_key)
        tid = self._type_id(project_key, "Story")
        if not (pid and tid and summary):
            return None
        filters = [
            {"project": {"operator": "=", "values": [pid]}},
            {"type": {"operator": "=", "values": [tid]}},
            {"subject": {"operator": "=", "values": [summary]}},
        ]
        hits = self.client.search_work_packages(filters, page_size=10)
        hit = hits[0] if hits else None
        if not hit:
            filters[-1] = {"subject": {"operator": "contains", "values": [summary]}}
            hits = self.client.search_work_packages(filters, page_size=10)
            hit = hits[0] if hits else None
        if not hit:
            return None
        # fetch full
        try:
            href = ((hit.get("_links") or {}).get("self") or {}).get("href")
            wid = href.rstrip("/").split("/")[-1] if isinstance(href, str) else None
            wp = self.client.work_package(wid) if wid else None
            if not wp:
                return None
            return {"key": str(wp.get("id")), "fields": self._map_current_fields(wp)}
        except Exception:
            return None

    # Compatibility helpers used by some scripts
    def update_issue(self, issue_key: str, fields: Dict[str, Any]) -> bool:
        ok, _, _, _ = self.update_issue_resilient(issue_key, fields)
        return ok

    def resolve_account_id(self, query: str) -> Optional[str]:
        # OpenProject user resolution not implemented; return None to skip assignment
        return None

    def find_story_by_order_id(self, project_key: str, order_id: str, epic_key: Optional[str] = None, fmap: Optional[TrackerFieldMap] = None) -> Optional[Dict[str, Any]]:
        # helper for a single project id search
        def _search_in_project(pid: str) -> Optional[Dict[str, Any]]:
            tid = self._type_id(project_key, "Story")
            if not (pid and tid and order_id):
                return None
            cf_map = (fmap.discovered_custom_fields if isinstance(fmap, TrackerFieldMap) else self._cf_map()) or {}
            low = {str(k).strip().lower(): v for k, v in cf_map.items()}
            fid = low.get("wpr wp order id") or low.get("wp order id")
            if not fid:
                return None
            filters = [
                {"project": {"operator": "=", "values": [pid]}},
                {"type": {"operator": "=", "values": [tid]}},
                {fid: {"operator": "=", "values": [str(order_id)]}},
            ]
            hits = self.client.search_work_packages(filters, page_size=5)
            if not hits:
                return None
            try:
                hit = hits[0]
                href = ((hit.get("_links") or {}).get("self") or {}).get("href")
                wid = href.rstrip("/").split("/")[-1] if isinstance(href, str) else None
                wp = self.client.work_package(wid) if wid else None
                if not wp:
                    return None
                return {"key": str(wp.get("id")), "fields": self._map_current_fields(wp)}
            except Exception:
                return None
        # try in target project
        pid = self._project_id(project_key)
        if pid:
            found = _search_in_project(pid)
            if found:
                return found
        # if not found and a parent is configured, search across child projects
        parent = (self.client.parent_project or self.client.cfg.get("parent_project") or None) if hasattr(self.client, 'parent_project') else (self.client.cfg.get("parent_project") if hasattr(self.client, 'cfg') else None)
        if not parent:
            parent = os.getenv("OPENPROJECT_PARENT_PROJECT")
        try:
            if parent:
                parent_obj = self.client._find_project_by_identifier_or_name(parent)
                if parent_obj:
                    ppid = str(parent_obj.get("id"))
                    for pr in self.client.list_projects():
                        ph = (((pr.get("_links") or {}).get("parent") or {}).get("href"))
                        if isinstance(ph, str) and ph.rstrip("/").endswith(f"/projects/{ppid}"):
                            cid = str(pr.get("id"))
                            found = _search_in_project(cid)
                            if found:
                                return found
        except Exception:
            pass
        return None

    def find_epic_by_order_id(self, project_key: str, order_id: str, fmap: Optional[TrackerFieldMap] = None) -> Optional[Dict[str, Any]]:
        def _search(pid: str) -> Optional[Dict[str, Any]]:
            tid = self._type_id(project_key, "Epic")
            if not (pid and tid and order_id):
                return None
            cf_map = (fmap.discovered_custom_fields if isinstance(fmap, TrackerFieldMap) else self._cf_map()) or {}
            low = {str(k).strip().lower(): v for k, v in cf_map.items()}
            for name in ("wpr bp id", "bp id", "wpr wp order id", "wp order id"):
                fid = low.get(name)
                if not fid:
                    continue
                filters = [
                    {"project": {"operator": "=", "values": [pid]}},
                    {"type": {"operator": "=", "values": [tid]}},
                    {fid: {"operator": "=", "values": [str(order_id)]}},
                ]
                hits = self.client.search_work_packages(filters, page_size=5)
                if hits:
                    try:
                        hit = hits[0]
                        href = ((hit.get("_links") or {}).get("self") or {}).get("href")
                        wid = href.rstrip("/").split("/")[-1] if isinstance(href, str) else None
                        wp = self.client.work_package(wid) if wid else None
                        if not wp:
                            continue
                        return {"key": str(wp.get("id")), "fields": self._map_current_fields(wp)}
                    except Exception:
                        continue
            return None
        pid = self._project_id(project_key)
        if pid:
            found = _search(pid)
            if found:
                return found
        parent = os.getenv("OPENPROJECT_PARENT_PROJECT")
        try:
            if parent:
                parent_obj = self.client._find_project_by_identifier_or_name(parent)
                if parent_obj:
                    ppid = str(parent_obj.get("id"))
                    for pr in self.client.list_projects():
                        ph = (((pr.get("_links") or {}).get("parent") or {}).get("href"))
                        if isinstance(ph, str) and ph.rstrip("/").endswith(f"/projects/{ppid}"):
                            cid = str(pr.get("id"))
                            found = _search(cid)
                            if found:
                                return found
        except Exception:
            pass
        return None
        
        # Try common names for the Order ID field
        order_fid = None
        for name in ("wpr wp order id", "wp order id", "wpr bp id", "bp id"):
            fid = low.get(name)
            if fid:
                order_fid = fid
                break
        
        if not order_fid:
            return {}

        # Fetch all Epics (pagination loop)
        epics_map = {}
        page = 1
        page_size = 100
        
        while True:
            filters = [
                {"project": {"operator": "=", "values": [pid]}},
                {"type": {"operator": "=", "values": [tid]}},
            ]
            
            try:
                results = self.client.search_work_packages(filters, page_size=page_size, offset=page)
            except Exception:
                break
                
            if not results:
                break
                
            for hit in results:
                try:
                    # Extract Order ID from the hit
                    oid = hit.get(order_fid)
                    if not oid:
                        continue
                    
                    oid_str = str(oid).strip()
                    if not oid_str:
                        continue
                        
                    # Map fields
                    fields = self._map_current_fields(hit)
                    
                    epics_map[oid_str] = {
                        "key": str(hit.get("id")),
                        "fields": fields,
                        "_raw": hit
                    }
                except Exception:
                    continue
            
            if len(results) < page_size:
                break
            page += 1
            
        return epics_map

    def compute_epic_diff(self, planned_fields: Dict[str, Any], current_fields: Dict[str, Any]) -> Dict[str, Any]:
        diff: Dict[str, Any] = {}
        if planned_fields.get("summary") and planned_fields.get("summary") != current_fields.get("summary"):
            diff["summary"] = planned_fields.get("summary")
        if planned_fields.get("description"):
            diff["description"] = planned_fields.get("description")
        # Include any custom fields in planned payload
        for k, v in planned_fields.items():
            if isinstance(k, str) and k.startswith("customField"):
                if current_fields.get(k) != v:
                    diff[k] = v
        return diff

    def compute_story_diff(self, planned_fields: Dict[str, Any], current_fields: Dict[str, Any]) -> Dict[str, Any]:
        diff: Dict[str, Any] = {}
        if planned_fields.get("summary") and planned_fields.get("summary") != current_fields.get("summary"):
            diff["summary"] = planned_fields.get("summary")
        if planned_fields.get("description"):
            diff["description"] = planned_fields.get("description")
        if ("duedate" in planned_fields) and (planned_fields.get("duedate") != current_fields.get("duedate")):
            diff["duedate"] = planned_fields.get("duedate")
        for k, v in planned_fields.items():
            if isinstance(k, str) and k.startswith("customField"):
                if current_fields.get(k) != v:
                    diff[k] = v
        return diff

    # ---------- Comments & URLs ----------
    def add_comment(self, issue_key: str, body: str) -> bool:
        try:
            return self.client.add_comment(issue_key, body)
        except Exception:
            return False

    def story_browse_url(self, project_base_url: str, key: str) -> str:
        return f"/api/v3/work_packages/{key}".replace("/api/v3", "").replace("//", "/")

    # ---------- Status mapping (best-effort) ----------
    def _canonical_wpr_status(self, s: str) -> str:
        low = (s or "").strip().lower()
        mapping = {
            "pending acknowledgement": "Pending Acknowledgement",
            "pending acknowledgment": "Pending Acknowledgement",
            "acknowledge": "Acknowledged",
            "acknowledged": "Acknowledged",
            "pending approval": "Pending Approval",
            "approved": "Approved",
            "objected": "Objected",
            "rejected": "Rejected",
            "cancelled": "Cancelled",
            "canceled": "Cancelled",
            "waiting for order submission": "Waiting for order submission",
        }
        return mapping.get(low, s)

    def _current_status_name(self, issue_key: str) -> Optional[str]:
        try:
            wp = self.client.work_package(issue_key) or {}
            status = (((wp.get("_embedded") or {}).get("status") or {}).get("name"))
            return str(status) if status else None
        except Exception:
            return None

    def _transition_issue_to(self, issue_key: str, target_status: str) -> bool:
        # In OP, status is updated via PATCH with _links.status and lockVersion
        wp = self.client.work_package(issue_key)
        if not wp:
            return False
        lock = int((wp or {}).get("lockVersion") or 0)
        # Attempt optimistic transition by resolving status id/href and PATCHing
        name = (target_status or "").strip()
        if not name:
            return False
        try:
            statuses = self.client.list_statuses() or {}
            tgt = statuses.get(name.lower())
            href = None
            if tgt:
                href = tgt.get("href") or (f"/api/v3/statuses/{tgt.get('id')}" if tgt.get("id") else None)
            if not href:
                log_kv("op_status_transition", ok=False, issue=issue_key, target=name, reason="status_not_found")
                return False
            payload: Dict[str, Any] = {"lockVersion": lock, "_links": {"status": {"href": href}}}
            status, body = self.client.update_work_package(issue_key, payload)
            ok = status in (200, 204)
            if not ok:
                log_kv("op_status_transition", ok=False, issue=issue_key, target=name, http=status)
            return ok
        except Exception as ex:
            log_kv("op_status_transition", ok=False, issue=issue_key, target=name, error=str(ex))
            return False

    def sync_epic_status_from_wpr(self, epic_key: Optional[str], planned_fields: Dict[str, Any], fieldmap: JiraFieldMap) -> None:
        # Best-effort: map WPR custom field value to built-in OP Status via configured mapping.
        try:
            if not epic_key:
                return
            cf = self._cf_map()
            fid = cf.get("wpr wp order status")
            if not fid:
                return
            raw = planned_fields.get(fid)
            if not isinstance(raw, (str,)):
                # When compiled via OP mapping, field may be set to {href:...}; skip in that case
                return
            # Use the canonical WPR status directly as the built-in Status target
            canon = self._canonical_wpr_status(str(raw))
            target = canon
            if not target:
                return
            cur = self._current_status_name(epic_key)
            if cur and str(cur).strip().lower() == target.strip().lower():
                return
            ok = self._transition_issue_to(epic_key, target)
            if not ok:
                log_kv("op_status_transition_warn", epic=epic_key, from_status=cur or "", to_status=target, reason="not_allowed_or_failed")
        except Exception:
            # Never fail the run for status transitions
            return

    # ---------- Optional helpers ----------
    def has_field_id_on_issuetype(self, project_key: str, field_id: str, issuetype_name: str) -> bool:
        # For OP, approximate: field is usable if it exists globally. We cannot easily check per-type availability without forms.
        return field_id in self._cf_map().values()
