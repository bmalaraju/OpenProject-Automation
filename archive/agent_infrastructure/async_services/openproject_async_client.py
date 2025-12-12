from __future__ import annotations

"""
Async OpenProject client (Phase 2, optional): httpx.AsyncClient + HTTP/2.

Provides minimal subset used by the service layer:
  - resolve_project
  - list_types_for_project
  - create_work_package
  - update_work_package
  - work_package
  - search_work_packages
  - work_package_form
  - list_custom_fields / list_custom_options
"""

from typing import Any, Dict, List, Optional, Tuple
import os
import json

import httpx
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None

from wpr_agent.clients.op_config import load_config as load_op_config  # type: ignore


class OpenProjectAsyncClient:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        self.cfg = cfg or load_op_config()
        self.base_url: str = (self.cfg.get("base_url") or "").rstrip("/")
        self.api_key: Optional[str] = self.cfg.get("api_key")
        if not self.base_url:
            raise RuntimeError("OpenProject base_url not configured")
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        self.client = httpx.AsyncClient(http2=True, limits=limits, timeout=30.0)

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/hal+json, application/json", "Content-Type": "application/json"}
        if self.api_key:
            basic_user = os.getenv("OPENPROJECT_BASIC_USER", "apikey")
            import base64
            token = base64.b64encode(f"{basic_user}:{self.api_key}".encode("utf-8")).decode("ascii")
            h["Authorization"] = f"Basic {token}"
        return h

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = self.base_url + path
        headers = {**self._headers(), **(kwargs.pop("headers", {}) or {})}
        tracer = get_tracer()
        span = None
        try:
            if tracer:
                span = tracer.start_trace("op.request.async", input={"method": method.upper(), "path": path})
        except Exception:
            span = None
        r = await self.client.request(method.upper(), url, headers=headers, **kwargs)
        try:
            if span:
                span.set_attribute("status", r.status_code)
                ct = r.headers.get("Content-Type", "")
                if ct:
                    span.set_attribute("content_type", ct)
                span.end()
        except Exception:
            pass
        return r

    # ---- Convenience APIs ----
    async def resolve_project(self, logical_key: str) -> Optional[Dict[str, Any]]:
        key = (logical_key or "").strip()
        if not key:
            return None
        # Try identifier match via filter
        filt = json.dumps([{ "identifier": { "operator": "=", "values": [ key ] } }])
        r = await self._request("GET", "/api/v3/projects", params={"filters": filt, "pageSize": 1})
        if r.status_code == 200:
            data = r.json() or {}
            elems = ((data.get("_embedded") or {}).get("elements") or [])
            if isinstance(elems, list) and elems:
                return elems[0]
        # Fallback: list and match by name
        r2 = await self._request("GET", "/api/v3/projects")
        if r2.status_code == 200:
            data = r2.json() or {}
            elems = ((data.get("_embedded") or {}).get("elements") or [])
            for pr in elems or []:
                try:
                    ident = str(pr.get("identifier") or "").strip()
                    name = str(pr.get("name") or "").strip()
                    if ident.lower() == key.lower() or name.lower() == key.lower():
                        return pr
                except Exception:
                    continue
        return None

    async def list_types_for_project(self, project_id: str | int) -> Dict[str, Any]:
        r = await self._request("GET", f"/api/v3/projects/{project_id}/types")
        by_name: Dict[str, Any] = {}
        if r.status_code == 200:
            try:
                data = r.json() or {}
                elems = ((data.get("_embedded") or {}).get("elements") or [])
                for t in elems or []:
                    nm = str(t.get("name") or "").strip()
                    if nm:
                        by_name[nm.lower()] = t
            except Exception:
                pass
        return by_name

    async def create_work_package(self, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        r = await self._request("POST", "/api/v3/work_packages", json=payload)
        try:
            body = r.json()
        except Exception:
            body = {"text": r.text}
        return r.status_code, body

    async def update_work_package(self, wp_id: str | int, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        r = await self._request("PATCH", f"/api/v3/work_packages/{wp_id}", json=payload)
        try:
            body = r.json()
        except Exception:
            body = {"text": r.text}
        return r.status_code, body

    async def work_package(self, wp_id: str | int) -> Optional[Dict[str, Any]]:
        r = await self._request("GET", f"/api/v3/work_packages/{wp_id}")
        return r.json() if r.status_code == 200 else None

    async def work_package_form(self, project_id: str | int, type_id: str | int) -> Tuple[int, Dict[str, Any]]:
        body = {"_links": {"project": {"href": f"/api/v3/projects/{project_id}"}, "type": {"href": f"/api/v3/types/{type_id}"}}}
        r = await self._request("POST", "/api/v3/work_packages/form", json=body)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}
        return r.status_code, data

    async def list_custom_fields(self) -> Dict[str, str]:
        r = await self._request("GET", "/api/v3/custom_fields")
        fields: Dict[str, str] = {}
        if r.status_code == 200:
            data = r.json() or {}
            items = ((data.get("_embedded") or {}).get("elements") or [])
            for cf in items:
                try:
                    nm = str(cf.get("name") or "").strip().lower()
                    cid = cf.get("_links", {}).get("self", {}).get("href") or ""
                    if nm and cid:
                        fields[nm] = cid.split("/")[-1] if "/" in cid else cid
                except Exception:
                    continue
        return fields

    async def list_custom_options(self) -> List[Dict[str, Any]]:
        r = await self._request("GET", "/api/v3/custom_options")
        if r.status_code == 200:
            try:
                data = r.json() or {}
                return ((data.get("_embedded") or {}).get("elements") or [])
            except Exception:
                return []
        return []

    async def list_statuses(self) -> Dict[str, Any]:
        """Return mapping name(lower) -> {id, href, name} for built-in statuses (async)."""
        try:
            r = await self._request("GET", "/api/v3/statuses")
            if r.status_code != 200:
                return {}
            data = r.json() or {}
            items = ((data.get("_embedded") or {}).get("elements") or [])
            out: Dict[str, Any] = {}
            for it in items or []:
                try:
                    nm = str(it.get("name") or "").strip()
                    _id = str(it.get("id") or "").strip()
                    href = ((it.get("_links") or {}).get("self") or {}).get("href") or (f"/api/v3/statuses/{_id}" if _id else None)
                    if nm and (_id or href):
                        out[nm.lower()] = {"id": _id, "href": href, "name": nm}
                except Exception:
                    continue
            return out
        except Exception:
            return {}
