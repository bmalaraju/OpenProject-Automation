from __future__ import annotations

"""
Minimal OpenProject REST client used by the service layer.

Key helpers:
- OpenProjectClient._request(method, path, params=None, json=None)
- project resolution by identifier (alias/lowecase fallback)
- discovery for types and custom fields
- work package create/update/search and comments

This client is intentionally thin; resilience and business logic live in callers.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import base64
import json
import os
import requests
import logging

logger = logging.getLogger(__name__)

try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None

from .op_config import load_config as load_op_config


class OpenProjectClient:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        self.cfg = cfg or load_op_config()
        self.base_url: str = (self.cfg.get("base_url") or "").rstrip("/")
        # OAuth-first
        self.username: Optional[str] = self.cfg.get("username")
        self.api_key: Optional[str] = self.cfg.get("api_key")
        self.client_id: Optional[str] = self.cfg.get("client_id") or os.getenv("OPENPROJECT_OAUTH_CLIENT_ID")
        self.client_secret: Optional[str] = self.cfg.get("client_secret") or os.getenv("OPENPROJECT_OAUTH_CLIENT_SECRET")
        self.auth_url: Optional[str] = self.cfg.get("auth_url") or os.getenv("OPENPROJECT_OAUTH_AUTH_URL")
        self.token_url: Optional[str] = self.cfg.get("token_url") or os.getenv("OPENPROJECT_OAUTH_TOKEN_URL")
        self.redirect_uri: Optional[str] = self.cfg.get("redirect_uri") or os.getenv("OPENPROJECT_REDIRECT_URI")
        self.scopes: str = self.cfg.get("scopes") or os.getenv("OPENPROJECT_OAUTH_SCOPES") or "api_v3"
        self.tokens_file: Optional[str] = self.cfg.get("tokens_file") or os.getenv("OP_TOKENS_JSON")
        self.parent_project: Optional[str] = self.cfg.get("parent_project") or os.getenv("OPENPROJECT_PARENT_PROJECT")
        # Tokens
        self.access_token: Optional[str] = self.cfg.get("access_token")
        self.refresh_token: Optional[str] = None
        if not self.access_token and self.tokens_file:
            try:
                if os.path.exists(self.tokens_file):
                    t = json.loads(open(self.tokens_file, "r", encoding="utf-8").read())
                    self.access_token = t.get("access_token")
                    self.refresh_token = t.get("refresh_token")
            except Exception:
                pass
        if not self.base_url:
            # Fallback to env if not in config
            self.base_url = (os.getenv("OPENPROJECT_URL") or "").rstrip("/")
            if not self.base_url:
                 # Warn but don't crash immediately, might be set later? 
                 # Actually better to raise if essential.
                 pass

        # HTTP session with connection pooling
        self.session = requests.Session()
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry  # type: ignore
            adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=Retry(total=0, backoff_factor=0))
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
        except Exception:
            pass

    # ---------- HTTP ----------
    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/hal+json, application/json", "Content-Type": "application/json"}
        # Prefer API key (Basic) when provided — per request to ignore OAuth for now
        if self.api_key:
            basic_user = os.getenv("OPENPROJECT_BASIC_USER", "apikey")
            token = base64.b64encode(f"{basic_user}:{self.api_key}".encode("utf-8")).decode("ascii")
            h["Authorization"] = f"Basic {token}"
            return h
        # Else use OAuth Bearer if available
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
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
                safe_meta = {
                    "method": method.upper(),
                    "path": path,
                }
                span = tracer.start_trace("op.request", input=safe_meta)
        except Exception:
            span = None
        
        try:
            r = self.session.request(method=method.upper(), url=url, headers=headers, timeout=30, **kwargs)
        except Exception as e:
            logger.error(f"OpenProject Request Error: {e}")
            if span:
                span.set_attribute("error", str(e))
                span.end()
            raise

        if r.status_code == 401 and self.access_token and self._refresh_access_token():
            headers = {**self._headers(), **(kwargs.get("headers") or {})}
            r = self.session.request(method=method.upper(), url=url, headers=headers, timeout=30, **kwargs)
        
        try:
            if span:
                span.set_attribute("status", r.status_code)
                ct = r.headers.get("Content-Type", "")
                if ct:
                    span.set_attribute("content_type", ct)
                # Basic rate-limit hints if present
                rl = r.headers.get("Retry-After") or r.headers.get("X-RateLimit-Remaining")
                if rl is not None:
                    span.set_attribute("rate_hint", str(rl))
                span.end()
        except Exception:
            pass
        return r

    # ---------- OAuth refresh ----------
    def _save_tokens(self, access: str, refresh: Optional[str]) -> None:
        if not self.tokens_file:
            return
        try:
            tokens: Dict[str, Any] = {}
            if os.path.exists(self.tokens_file):
                try:
                    tokens = json.loads(open(self.tokens_file, "r", encoding="utf-8").read())
                except Exception:
                    tokens = {}
            tokens["access_token"] = access
            if refresh:
                tokens["refresh_token"] = refresh
            os.makedirs(os.path.dirname(self.tokens_file), exist_ok=True)
            with open(self.tokens_file, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(tokens, indent=2))
        except Exception:
            pass

    def _refresh_access_token(self) -> bool:
        try:
            if not (self.token_url and self.client_id and self.client_secret):
                return False
            # Find refresh token
            refresh = self.refresh_token
            if not refresh and self.tokens_file and os.path.exists(self.tokens_file):
                try:
                    t = json.loads(open(self.tokens_file, "r", encoding="utf-8").read())
                    refresh = t.get("refresh_token")
                except Exception:
                    refresh = None
            if not refresh:
                return False
            body = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh,
            }
            r = requests.post(self.token_url, headers={"Content-Type": "application/json"}, json=body, timeout=30)
            if r.status_code != 200:
                return False
            data = r.json() or {}
            new_access = data.get("access_token")
            new_refresh = data.get("refresh_token") or refresh
            if not new_access:
                return False
            self.access_token = new_access
            self.refresh_token = new_refresh
            self._save_tokens(new_access, new_refresh)
            # Optionally write to working config JSON (non-fatal on errors)
            try:
                cfg_path = os.getenv("WP_OP_CONFIG_PATH") or os.path.join("wpr_agent", "config", "working_openproject_config.json")
                obj = {}
                if os.path.exists(cfg_path):
                    obj = json.loads(open(cfg_path, "r", encoding="utf-8").read())
                obj["access_token"] = new_access
                obj.setdefault("token_url", self.token_url)
                obj.setdefault("tokens_file", self.tokens_file or "")
                os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
                with open(cfg_path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(obj, indent=2))
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _get_paginated(self, path: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        url = path
        q = params or {}
        # Use offset pagination
        page = 1
        while True:
            qp = dict(q)
            qp.setdefault("pageSize", 100)
            qp.setdefault("page", page)
            r = self._request("GET", url, params=qp)
            if r.status_code != 200:
                break
            try:
                data = r.json() or {}
            except Exception:
                data = {}
            embedded = data.get("_embedded") or {}
            elems = embedded.get("elements") or []
            if isinstance(elems, list):
                items.extend([e for e in elems if isinstance(e, dict)])
            # Detect next page
            total = data.get("total")
            count = data.get("count")
            if total is None or count is None:
                # Fallback: stop when fewer than pageSize were returned
                if not elems or len(elems) < int(qp.get("pageSize", 100)):
                    break
            if (page * int(qp.get("pageSize", 100))) >= int(total or 0):
                break
            page += 1
        return items

    # ---------- Project resolution ----------
    def _alias_map(self) -> Dict[str, str]:
        try:
            p = os.getenv("OP_PROJECT_ALIAS_MAP") or os.path.join("wpr_agent", "config", "project_alias_map.json")
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
            reg = data.get("registry") if isinstance(data, dict) else data
            return {str(k): str(v) for k, v in (reg or {}).items()}
        except Exception:
            return {}

    def resolve_project(self, logical_key: str) -> Optional[Dict[str, Any]]:
        key = (logical_key or "").strip()
        if not key:
            return None
        # If parent is configured, resolve as subproject under parent
        if self.parent_project:
            parent = self._find_project_by_identifier_or_name(self.parent_project)
            if not parent:
                return None
            pid = str(parent.get("id") or "").strip()
            if not pid:
                return None
            # Determine candidate identifier for child
            child_id = self._alias_map().get(key) or key.lower()
            # Search under parent using full project list (pagination)
            items = self._get_paginated("/api/v3/projects")
            for pr in items:
                try:
                    # Check parent link
                    parent_href = (((pr.get("_links") or {}).get("parent") or {}).get("href"))
                    if not (isinstance(parent_href, str) and parent_href.rstrip("/").endswith(f"/projects/{pid}")):
                        continue
                    ident = str(pr.get("identifier") or "").strip()
                    name = str(pr.get("name") or "").strip()
                    if ident.lower() == child_id.lower() or name.lower() == key.lower():
                        return pr
                except Exception:
                    continue
            return None

        # 1) direct numeric id
        if key.isdigit():
            r = self._request("GET", f"/api/v3/projects/{key}")
            if r.status_code == 200:
                return r.json()
        # 2) try exact identifier via filters
        filt = json.dumps([{ "identifier": { "operator": "=", "values": [ key ] } }])
        r = self._request("GET", "/api/v3/projects", params={"filters": filt, "pageSize": 1})
        if r.status_code == 200:
            try:
                data = r.json() or {}
                elems = ((data.get("_embedded") or {}).get("elements") or [])
                if isinstance(elems, list) and elems:
                    return elems[0]
            except Exception:
                pass
        # 3) lowercase fallback
        low = key.lower()
        if low != key:
            filt2 = json.dumps([{ "identifier": { "operator": "=", "values": [ low ] } }])
            r2 = self._request("GET", "/api/v3/projects", params={"filters": filt2, "pageSize": 1})
            if r2.status_code == 200:
                try:
                    data = r2.json() or {}
                    elems = ((data.get("_embedded") or {}).get("elements") or [])
                    if isinstance(elems, list) and elems:
                        return elems[0]
                except Exception:
                    pass
        # 3b) fallback: scan all projects and match by identifier or name (case-insensitive)
        try:
            scanned = self._find_project_by_identifier_or_name(key)
            if scanned:
                return scanned
        except Exception:
            pass
        # 4) alias map
        alias = self._alias_map().get(key) or self._alias_map().get(low)
        if alias:
            return self.resolve_project(alias)
        return None

    def _find_project_by_identifier_or_name(self, ident_or_name: str) -> Optional[Dict[str, Any]]:
        s = (ident_or_name or "").strip()
        if not s:
            return None
        # Try by identifier via filters
        try:
            filt = json.dumps([{ "identifier": { "operator": "=", "values": [ s ] } }])
            r = self._request("GET", "/api/v3/projects", params={"filters": filt, "pageSize": 1})
            if r.status_code == 200:
                data = r.json() or {}
                elems = ((data.get("_embedded") or {}).get("elements") or [])
                if isinstance(elems, list) and elems:
                    return elems[0]
        except Exception:
            pass
        # Fallback: scan all and match by name
        items = self._get_paginated("/api/v3/projects")
        for pr in items:
            try:
                ident = str(pr.get("identifier") or "").strip()
                name = str(pr.get("name") or "").strip()
                if ident.lower() == s.lower() or name.lower() == s.lower():
                    return pr
            except Exception:
                continue
        return None

    # ---------- Types & Custom fields ----------
    def list_types_for_project(self, project_id: str | int) -> Dict[str, Any]:
        # GET /api/v3/projects/{id}/types
        r = self._request("GET", f"/api/v3/projects/{project_id}/types")
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

    def list_custom_fields(self) -> Dict[str, str]:
        # Returns mapping display name (lower) -> attribute key 'customField{id}'
        fields: Dict[str, str] = {}
        items = self._get_paginated("/api/v3/custom_fields", params={"pageSize": 100})
        for cf in items:
            try:
                nm = str(cf.get("name") or "").strip()
                cid = str(cf.get("id") or "").strip()
                if nm and cid:
                    fields[nm.lower()] = f"customField{cid}"
            except Exception:
                continue
        return fields

    def list_projects(self) -> List[Dict[str, Any]]:
        return self._get_paginated("/api/v3/projects")

    def list_statuses(self) -> Dict[str, Any]:
        """Return mapping name(lower) -> {id, href, name} for built-in statuses.

        Best-effort: if endpoint unavailable or errors, returns empty map.
        """
        try:
            r = self._request("GET", "/api/v3/statuses")
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

    def create_project(self, name: str, identifier: str, parent_id: Optional[str | int] = None) -> Tuple[int, Dict[str, Any]]:
        body: Dict[str, Any] = {"name": name, "identifier": identifier}
        if parent_id:
            body.setdefault("_links", {}).setdefault("parent", {"href": f"/api/v3/projects/{parent_id}"})
        r = self._request("POST", "/api/v3/projects", json=body)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}
        return r.status_code, data

    def list_global_types(self) -> Dict[str, Any]:
        r = self._request("GET", "/api/v3/types")
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

    def set_project_types(self, project_id: str | int, type_ids: List[str | int]) -> Tuple[int, Dict[str, Any]]:
        links = [{"href": f"/api/v3/types/{tid}"} for tid in type_ids]
        body = {"_links": {"types": links}}
        r = self._request("PATCH", f"/api/v3/projects/{project_id}", json=body)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}
        return r.status_code, data

    # ---------- Work packages ----------
    def work_package(self, wp_id: str | int) -> Optional[Dict[str, Any]]:
        r = self._request("GET", f"/api/v3/work_packages/{wp_id}")
        return r.json() if r.status_code == 200 else None

    def create_work_package(self, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        r = self._request("POST", "/api/v3/work_packages", json=payload)
        return r.status_code, (r.json() if r.headers.get("Content-Type", "").startswith("application/") else {"text": r.text})

    def update_work_package(self, wp_id: str | int, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        r = self._request("PATCH", f"/api/v3/work_packages/{wp_id}", json=payload)
        try:
            body = r.json()
        except Exception:
            body = {"text": r.text}
        return r.status_code, body

    def work_package_form(self, project_id: str | int, type_id: str | int, draft: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
        """Fetch a work package form (schema) for a given project and type.

        Returns (status, json). On success (200), json contains the field schema
        including allowed values for list custom fields.
        """
        body: Dict[str, Any] = {
            "_links": {
                "project": {"href": f"/api/v3/projects/{project_id}"},
                "type": {"href": f"/api/v3/types/{type_id}"},
            },
        }
        if draft:
            body.update(draft)
        r = self._request("POST", "/api/v3/work_packages/form", json=body)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}
        return r.status_code, data

    def search_work_packages(self, filters: List[Dict[str, Any]], page_size: int = 50) -> List[Dict[str, Any]]:
        try:
            filt = json.dumps(filters)
        except Exception:
            filt = "[]"
        r = self._request("GET", "/api/v3/work_packages", params={"filters": filt, "pageSize": page_size})
        if r.status_code != 200:
            return []
        try:
            data = r.json() or {}
            elems = ((data.get("_embedded") or {}).get("elements") or [])
            return elems if isinstance(elems, list) else []
        except Exception:
            return []

    def add_comment(self, wp_id: str | int, markdown: str) -> bool:
        body = {"comment": {"raw": str(markdown or ""), "format": "markdown"}}
        r = self._request("POST", f"/api/v3/work_packages/{wp_id}/activities", json=body)
        if r.status_code in (200, 201):
            return True
        # Fallback without format param
        body = {"comment": {"raw": str(markdown or "")}}
        r = self._request("POST", f"/api/v3/work_packages/{wp_id}/activities", json=body)
        return r.status_code in (200, 201)

    def list_custom_options(self) -> List[Dict[str, Any]]:
        """Return a list of global custom options (best-effort)."""
        items: List[Dict[str, Any]] = []
        try:
            r = self._request("GET", "/api/v3/custom_options")
            if r.status_code != 200:
                return []
            data = r.json() or {}
            elems = ((data.get("_embedded") or {}).get("elements") or [])
            if isinstance(elems, list):
                for e in elems:
                    if isinstance(e, dict):
                        items.append(e)
        except Exception:
            return []
        return items

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        # This requires admin or specific filter permissions usually
        params = {"filters": f'[{{"email": {{"operator": "=", "values": ["{email}"]}}}}]'}
        resp = self._request("GET", "/api/v3/users", params=params)
        if resp.status_code == 200:
            data = resp.json()
            embedded = data.get("_embedded", {})
            elements = embedded.get("elements", [])
            if elements:
                return elements[0]
        return None
