from __future__ import annotations

"""
OpenProject OAuth 2.0 authorization helper.

Usage:
  python wpr_agent/scripts/op_oauth_reauth.py --auth-url http://.../oauth/authorize --token-url http://.../oauth/token \
      --client-id XXX --client-secret YYY --redirect-uri http://localhost:3535/callback --scopes api_v3 --tokens wpr_agent/config/op_oauth_tokens.json

Steps:
  1) Prints an authorize URL; open it, consent, and get redirected to redirect_uri?code=....
  2) Paste the 'code' back to the script; it exchanges for access/refresh tokens and writes tokens JSON.
"""

import argparse
import json
import os
import sys
from pathlib import Path
import urllib.parse

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="OpenProject OAuth2 re-auth helper")
    ap.add_argument("--auth-url", default=os.getenv("OPENPROJECT_OAUTH_AUTH_URL"))
    ap.add_argument("--token-url", default=os.getenv("OPENPROJECT_OAUTH_TOKEN_URL"))
    ap.add_argument("--client-id", default=os.getenv("OPENPROJECT_OAUTH_CLIENT_ID"))
    ap.add_argument("--client-secret", default=os.getenv("OPENPROJECT_OAUTH_CLIENT_SECRET"))
    ap.add_argument("--redirect-uri", default=os.getenv("OPENPROJECT_REDIRECT_URI", "http://localhost:3535/callback"))
    ap.add_argument("--scopes", default=os.getenv("OPENPROJECT_OAUTH_SCOPES", "api_v3"))
    ap.add_argument("--tokens", default=os.getenv("OP_TOKENS_JSON", "wpr_agent/config/op_oauth_tokens.json"))
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if not all([args.auth_url, args.token_url, args.client_id, args.client_secret, args.redirect_uri]):
        print(json.dumps({"error": "Missing OAuth env/args"}, indent=2))
        raise SystemExit(1)
    params = {
        "client_id": args.client_id,
        "redirect_uri": args.redirect_uri,
        "response_type": "code",
        "scope": args.scopes,
    }
    url = args.auth_url
    sep = '&' if '?' in (url or '') else '?'
    auth_link = f"{url}{sep}{urllib.parse.urlencode(params)}"
    print("OpenProject OAuth authorize URL:")
    print(auth_link)
    code = input("Paste the 'code' from the redirected URL here: ").strip()
    if not code:
        print(json.dumps({"error": "No code provided"}, indent=2))
        raise SystemExit(1)
    body = {
        "grant_type": "authorization_code",
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "code": code,
        "redirect_uri": args.redirect_uri,
    }
    r = requests.post(args.token_url, headers={"Content-Type": "application/json"}, json=body, timeout=30)
    if r.status_code != 200:
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}
        print(json.dumps({"error": "Token exchange failed", "status": r.status_code, "body": data}, indent=2))
        raise SystemExit(1)
    data = r.json() or {}
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    Path(args.tokens).parent.mkdir(parents=True, exist_ok=True)
    Path(args.tokens).write_text(json.dumps({"access_token": access_token, "refresh_token": refresh_token}, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "tokens_file": args.tokens}, indent=2))


if __name__ == "__main__":
    main()

