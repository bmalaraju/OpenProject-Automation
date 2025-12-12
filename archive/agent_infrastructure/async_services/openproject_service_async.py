from __future__ import annotations

"""
Async OpenProject service (Phase 2). Minimal support for create/update Story/Epic with cached form/options.
"""

from typing import Any, Dict, Optional, Tuple
import asyncio

from wpr_agent.services.openproject_async_client import OpenProjectAsyncClient  # type: ignore
from wpr_agent.router.utils import log_kv
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None


class OpenProjectServiceV2Async:
    def __init__(self) -> None:
        self.client = OpenProjectAsyncClient()
        self._project_cache: Dict[str, Dict[str, Any]] = {}
        self._types_cache: Dict[str, Dict[str, Any]] = {}
        self._form_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._options_map: Optional[Dict[str, str]] = None
        self._cf_name_to_id: Optional[Dict[str, str]] = None
        self._overrides: Optional[Dict[str, Dict[str, str]]] = None

    async def _project_id(self, project_key: str) -> Optional[str]:
        if project_key in self._project_cache:
            try:
                return str(self._project_cache[project_key].get("id"))
            except Exception:
                return None
        obj = await self.client.resolve_project(project_key)
        if obj:
            self._project_cache[project_key] = obj
            try:
                return str(obj.get("id"))
            except Exception:
                return None
        return None

    async def _type_id(self, project_key: str, name: str) -> Optional[str]:
        pid = await self._project_id(project_key)
        if not pid:
            return None
        if pid in self._types_cache:
            m = self._types_cache[pid]
        else:
            m = await self.client.list_types_for_project(pid)
            self._types_cache[pid] = m
        key = (name or "").strip().lower()
        alias = {"story": "user story", "userstory": "user story", "epic": "epic", "task": "task"}.get(key, key)
        return str((m.get(alias) or {}).get("id") or "").strip() or None

    async def _form_schema(self, project_key: str, type_name: str) -> Dict[str, Any]:
        pid = await self._project_id(project_key)
        tid = await self._type_id(project_key, type_name)
        if not (pid and tid):
            return {}
        key = (pid, tid)
        if key in self._form_cache:
            return self._form_cache[key]
        status, data = await self.client.work_package_form(pid, tid)
        if status == 200 and isinstance(data, dict):
            self._form_cache[key] = data
            return data
        return {}

    async def _cf_map(self) -> Dict[str, str]:
        """Map custom field display name (lower) -> attribute key 'customField{id}'."""
        if self._cf_name_to_id is not None:
            return self._cf_name_to_id
        try:
            raw = await self.client.list_custom_fields()
            # raw maps name -> id (numeric or href tail). Normalize to 'customField{id}'.
            m: Dict[str, str] = {}
            for name, cid in (raw or {}).items():
                try:
                    s = str(cid)
                    s = s.split("/")[-1] if "/" in s else s
                    if s and s.isdigit():
                        m[str(name).strip().lower()] = f"customField{s}"
                    else:
                        # If already in 'customField{id}' form
                        if str(cid).startswith("customField"):
                            m[str(name).strip().lower()] = str(cid)
                except Exception:
                    continue
            self._cf_name_to_id = m
        except Exception:
            self._cf_name_to_id = {}
        return self._cf_name_to_id or {}

    async def _status_title_to_href(self, project_key: str, type_name: str, title: str) -> Optional[str]:
        """Resolve a status option title to its href using form schema, global options, or overrides."""
        canon_map = {
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
        sval = (title or "").strip()
        canon = canon_map.get(sval.lower(), sval)
        # Try form schema allowed values first
        try:
            schema_data = await self._form_schema(project_key, type_name)
            schema = schema_data.get("schema") or {}
            # Identify the status field key (customFieldXX)
            cf = await self._cf_map()
            status_fid = cf.get("wpr wp order status")
            if status_fid:
                fmeta = schema.get(status_fid) or {}
                allowed = None
                try:
                    allowed = ((fmeta.get("_links") or {}).get("allowedValues"))
                except Exception:
                    allowed = None
                if not allowed:
                    allowed = fmeta.get("allowedValues")
                if isinstance(allowed, list):
                    for opt in allowed:
                        try:
                            t = str(opt.get("title") or opt.get("name") or "")
                            href = ((opt.get("_links") or {}).get("self") or {}).get("href") or opt.get("href")
                            if href and t and t.strip().lower() == canon.strip().lower():
                                return href
                        except Exception:
                            continue
        except Exception:
            pass
        # Fallback to global custom_options
        try:
            opts = await self.client.list_custom_options()
            for opt in opts or []:
                try:
                    t = str(opt.get("title") or opt.get("name") or "")
                    href = ((opt.get("_links") or {}).get("self") or {}).get("href") or opt.get("href")
                    if href and t and t.strip().lower() == canon.strip().lower():
                        return href
                except Exception:
                    continue
        except Exception:
            pass
        # Fallback to local overrides file if present
        try:
            data = await self._load_overrides()
            # Try to resolve by display name key as a generic fallback
            href = (data.get("WPR WP Order Status") or {}).get(canon)
            if href:
                return href
        except Exception:
            pass
        return None

    async def _load_overrides(self) -> Dict[str, Dict[str, str]]:
        if self._overrides is not None:
            return self._overrides
        import os, json
        p = os.getenv("OP_CUSTOM_OPTION_OVERRIDES_PATH") or os.path.join("wpr_agent", "config", "op_custom_option_overrides.json")
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
                # Normalize mapping
                out: Dict[str, Dict[str, str]] = {}
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            out[str(k)] = {str(kk): str(vv) for kk, vv in v.items()}
                self._overrides = out
        except Exception:
            self._overrides = {}
        return self._overrides

    async def create_issue(self, project_key: str, type_name: str, fields: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        tracer = get_tracer()
        span = None
        try:
            if tracer:
                span = tracer.start_trace("op.service.create.async", input={"project_key": project_key, "type": type_name})
        except Exception:
            span = None
        pid = await self._project_id(project_key)
        tid = await self._type_id(project_key, type_name)
        if not pid or not tid:
            try:
                if span:
                    span.set_attribute("ok", False)
                    span.set_attribute("reason", "project/type unresolved")
                    span.end()
            except Exception:
                pass
            return False, {"error": "project/type unresolved"}
        payload: Dict[str, Any] = {}
        payload["subject"] = fields.get("summary") or ""
        if "description" in fields:
            payload["description"] = {"raw": fields.get("description") or "", "format": "markdown"}
        payload.setdefault("_links", {}).setdefault("project", {"href": f"/api/v3/projects/{pid}"})
        payload.setdefault("_links", {}).setdefault("type", {"href": f"/api/v3/types/{tid}"})
        if "duedate" in fields:
            payload["dueDate"] = fields.get("duedate")
        parent = (fields.get("parent") or {}).get("key") if isinstance(fields.get("parent"), dict) else None
        if parent:
            payload.setdefault("_links", {}).setdefault("parent", {"href": f"/api/v3/work_packages/{parent}"})
        # Custom fields: propagate non-blank values, mapping status titles to option hrefs
        try:
            cf = await self._cf_map()
            status_fid = cf.get("wpr wp order status")
        except Exception:
            cf, status_fid = {}, None
        for k, v in list((fields or {}).items()):
            if isinstance(k, str) and k.startswith("customField"):
                try:
                    if v is None or (isinstance(v, str) and v.strip() == ""):
                        continue
                except Exception:
                    pass
                # If this is a list-type like status, map string title to option href when possible
                href = None
                if isinstance(v, str):
                    # 1) Try overrides by explicit field id key (e.g., 'customField10')
                    try:
                        ov = await self._load_overrides()
                        href = (ov.get(k) or {}).get(v) or (ov.get(k) or {}).get(v.strip())
                    except Exception:
                        href = None
                    # 2) If this is the known status field, try schema/global options
                    if not href and status_fid and k == status_fid:
                        href = await self._status_title_to_href(project_key, type_name, v)
                    # 3) Generic fallback to display-name bucket
                    if not href:
                        try:
                            ov = await self._load_overrides()
                            href = (ov.get("WPR WP Order Status") or {}).get(v) or (ov.get("WPR WP Order Status") or {}).get(v.strip())
                        except Exception:
                            href = None
                if href:
                    payload[k] = {"href": href}
                else:
                    payload[k] = v
        # Submit
        status, body = await self.client.create_work_package(payload)
        try:
            if span:
                span.set_attribute("status", int(status))
                span.set_attribute("ok", bool(status in (200, 201)))
                span.end()
        except Exception:
            pass
        return (status in (200, 201)), body

    async def update_issue(self, issue_key: str, project_key: str, type_name: str, fields: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        tracer = get_tracer()
        span = None
        try:
            if tracer:
                span = tracer.start_trace("op.service.update.async", input={"project_key": project_key, "type": type_name, "issue": str(issue_key)})
        except Exception:
            span = None
        pid = await self._project_id(project_key)
        tid = await self._type_id(project_key, type_name)
        if not pid or not tid:
            try:
                if span:
                    span.set_attribute("ok", False)
                    span.set_attribute("reason", "project/type unresolved")
                    span.end()
            except Exception:
                pass
            return False, {"error": "project/type unresolved"}
        wp = await self.client.work_package(issue_key)
        lock = int((wp or {}).get("lockVersion") or 0)
        payload: Dict[str, Any] = {}
        payload["subject"] = fields.get("summary") or ""
        if "description" in fields:
            payload["description"] = {"raw": fields.get("description") or "", "format": "markdown"}
        payload["lockVersion"] = lock
        status, body = await self.client.update_work_package(issue_key, payload)
        try:
            if span:
                span.set_attribute("status", int(status))
                span.set_attribute("ok", bool(status in (200, 204)))
                span.end()
        except Exception:
            pass
        return (status in (200, 204)), body



    async def sync_epic_status_from_wpr(self, epic_key: Optional[str], project_key: str, planned_fields: Dict[str, Any]) -> bool:
        try:
            if not epic_key:
                return False
            cf = await self._cf_map()
            fid = cf.get("wpr wp order status")
            if not fid:
                return False
            raw = planned_fields.get(fid)
            if not isinstance(raw, (str,)):
                return False
            canon_map = {
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
            # Use canonical WPR status directly as target OP built-in Status name
            target = canon_map.get(str(raw).strip().lower(), str(raw).strip())
            # Fetch current
            wp = await self.client.work_package(epic_key)
            if not wp:
                return False
            try:
                cur = (((wp.get("_embedded") or {}).get("status") or {}).get("name"))
            except Exception:
                cur = None
            if cur and str(cur).strip().lower() == target.strip().lower():
                return True
            statuses = await self.client.list_statuses()
            tgt = statuses.get(target.strip().lower()) if isinstance(statuses, dict) else None
            href = None
            if tgt:
                href = tgt.get("href") or (f"/api/v3/statuses/{tgt.get('id')}" if tgt.get("id") else None)
            if not href:
                log_kv("op_status_transition_async", ok=False, epic=epic_key, target=target, reason="status_not_found")
                return False
            lock = int((wp or {}).get("lockVersion") or 0)
            payload = {"lockVersion": lock, "_links": {"status": {"href": href}}}
            status, body = await self.client.update_work_package(epic_key, payload)
            ok = status in (200, 204)
            if not ok:
                log_kv("op_status_transition_async", ok=False, epic=epic_key, target=target, http=status)
            return ok
        except Exception as ex:
            log_kv("op_status_transition_async", ok=False, epic=str(epic_key or ''), error=str(ex))
            return False

