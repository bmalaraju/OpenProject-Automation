from __future__ import annotations

"""
Configuration loader for OpenProject client.

Priority:
1. Explicit path in env WP_OP_CONFIG_PATH (JSON with keys like base_url, api_key, username)
2. Environment variables: OPENPROJECT_BASE_URL, OPENPROJECT_API_KEY, OPENPROJECT_USERNAME
3. Repository-local default: wpr_agent/config/working_openproject_config.json (if present)

Never commit secrets. This loader only reads from local machine state.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_config() -> Dict[str, Any]:
    # 1) explicit path
    cfg_path = os.getenv("WP_OP_CONFIG_PATH")
    if cfg_path:
        p = Path(cfg_path)
        if p.exists():
            data = _load_json(p)
            if data:
                return data

    # 2) env vars
    base_url = os.getenv("OPENPROJECT_BASE_URL")
    # OAuth-first config (preferred)
    oauth_client_id = os.getenv("OPENPROJECT_OAUTH_CLIENT_ID")
    oauth_client_secret = os.getenv("OPENPROJECT_OAUTH_CLIENT_SECRET")
    oauth_auth_url = os.getenv("OPENPROJECT_OAUTH_AUTH_URL")
    oauth_token_url = os.getenv("OPENPROJECT_OAUTH_TOKEN_URL")
    redirect_uri = os.getenv("OPENPROJECT_REDIRECT_URI")
    scopes = os.getenv("OPENPROJECT_OAUTH_SCOPES") or "api_v3"
    tokens_file = os.getenv("OP_TOKENS_JSON")
    access_token = os.getenv("OPENPROJECT_ACCESS_TOKEN")
    parent_project = os.getenv("OPENPROJECT_PARENT_PROJECT")

    if base_url and (oauth_client_id and oauth_client_secret) and (tokens_file or access_token):
        cfg: Dict[str, Any] = {
            "base_url": base_url,
            "client_id": oauth_client_id,
            "client_secret": oauth_client_secret,
            "auth_url": oauth_auth_url,
            "token_url": oauth_token_url,
            "redirect_uri": redirect_uri,
            "scopes": scopes,
        }
        if tokens_file:
            cfg["tokens_file"] = tokens_file
        if access_token:
            cfg["access_token"] = access_token
        if parent_project:
            cfg["parent_project"] = parent_project
        return cfg

    # Legacy API key config (not used for auth when OAuth present)
    api_key = os.getenv("OPENPROJECT_API_KEY")
    username = os.getenv("OPENPROJECT_USERNAME")
    if base_url and api_key and username:
        cfg = {
            "base_url": base_url,
            "api_key": api_key,
            "username": username,
        }
        if parent_project:
            cfg["parent_project"] = parent_project
        return cfg

    # 3) repo-local default
    # Updated path to point to wpr_agent/config
    repo_local = Path("wpr_agent") / "config" / "working_openproject_config.json"
    if repo_local.exists():
        data = _load_json(repo_local)
        if data:
            return data

    return {}
