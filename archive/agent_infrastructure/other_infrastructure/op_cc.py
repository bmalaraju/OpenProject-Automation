from __future__ import annotations

from typing import Optional, Dict, Any
import os
import json
import time

import requests


def fetch_client_credentials_token(
    *,
    token_url: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    scope: Optional[str] = None,
    tokens_path: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Fetch a fresh access token via OAuth2 Client Credentials and write to tokens JSON.

    Inputs taken from env when args are None:
      - OPENPROJECT_OAUTH_TOKEN_URL, OPENPROJECT_OAUTH_CLIENT_ID, OPENPROJECT_OAUTH_CLIENT_SECRET
      - OPENPROJECT_OAUTH_SCOPES (optional; default: api_v3)
      - OP_TOKENS_JSON (default: wpr_agent/config/op_oauth_tokens.json)

    Returns a dict with at least { ok: bool, status: int, access_token?: str, error?: str }
    """
    url = (token_url or os.getenv("OPENPROJECT_OAUTH_TOKEN_URL") or "").strip()
    cid = (client_id or os.getenv("OPENPROJECT_OAUTH_CLIENT_ID") or "").strip()
    csecret = (client_secret or os.getenv("OPENPROJECT_OAUTH_CLIENT_SECRET") or "").strip()
    scp = (scope or os.getenv("OPENPROJECT_OAUTH_SCOPES") or "api_v3").strip()
    out_path = tokens_path or os.getenv("OP_TOKENS_JSON") or os.path.join("wpr_agent", "config", "op_oauth_tokens.json")

    if not (url and cid and csecret):
        return {"ok": False, "status": 0, "error": "missing client_credentials env (token_url/client_id/client_secret)"}

    data = {
        "grant_type": "client_credentials",
        "client_id": cid,
        "client_secret": csecret,
    }
    if scp:
        data["scope"] = scp
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        r = requests.post(url, data=data, headers=headers, timeout=timeout)
    except Exception as ex:
        return {"ok": False, "status": 0, "error": str(ex)}
    if r.status_code != 200:
        try:
            body = r.json()
        except Exception:
            body = {"text": r.text}
        return {"ok": False, "status": r.status_code, "error": body}
    try:
        body = r.json() or {}
    except Exception:
        body = {}
    token = body.get("access_token")
    if not token:
        return {"ok": False, "status": r.status_code, "error": "no access_token in response"}
    # Persist tokens JSON (access only; no refresh in client_credentials)
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"access_token": token, "fetched_at": int(time.time())}, indent=2))
    except Exception:
        # soft-fail write; still return token
        pass
    # Also expose to current process env for immediate use if desired
    os.environ["OPENPROJECT_ACCESS_TOKEN"] = token
    return {"ok": True, "status": r.status_code, "access_token": token, "tokens_file": out_path}

