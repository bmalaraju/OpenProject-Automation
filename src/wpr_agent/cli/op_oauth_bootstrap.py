from __future__ import annotations

"""
OpenProject OAuth2 bootstrap (automated): spins a local HTTP server to capture the code.

Reads env (or args) for OP OAuth settings, opens the browser to the authorize URL,
captures the 'code' via redirect to the local server, exchanges for tokens, and writes
to tokens JSON. Run once per machine to obtain refresh tokens (then auto-refresh works).
"""

import argparse
import http.server
import json
import os
import socket
import threading
import urllib.parse
from pathlib import Path
import webbrowser

import requests
from dotenv import load_dotenv


def _parse_redirect(uri: str) -> tuple[str, int, str]:
    # Return (host, port, path)
    p = urllib.parse.urlparse(uri)
    host = p.hostname or "127.0.0.1"
    port = p.port or 3535
    path = p.path or "/callback"
    return host, port, path


class _Handler(http.server.BaseHTTPRequestHandler):
    code_holder: dict = {"code": None}

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        code = (qs.get("code") or [None])[0]
        _Handler.code_holder["code"] = code
        body = b"<html><body>OpenProject auth complete. You can close this tab.</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args):  # suppress
        return


def _serve_one(host: str, port: int) -> None:
    with http.server.HTTPServer((host, port), _Handler) as httpd:
        httpd.timeout = 300
        # serve a single request or until code captured
        while _Handler.code_holder.get("code") is None:
            httpd.handle_request()


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1].parent / ".env", override=False)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    ap = argparse.ArgumentParser(description="Automated OpenProject OAuth bootstrap")
    ap.add_argument("--auth-url", default=os.getenv("OPENPROJECT_OAUTH_AUTH_URL"))
    ap.add_argument("--token-url", default=os.getenv("OPENPROJECT_OAUTH_TOKEN_URL"))
    ap.add_argument("--client-id", default=os.getenv("OPENPROJECT_OAUTH_CLIENT_ID"))
    ap.add_argument("--client-secret", default=os.getenv("OPENPROJECT_OAUTH_CLIENT_SECRET"))
    ap.add_argument("--redirect-uri", default=os.getenv("OPENPROJECT_REDIRECT_URI", "http://localhost:3535/callback"))
    ap.add_argument("--scopes", default=os.getenv("OPENPROJECT_OAUTH_SCOPES", "api_v3"))
    ap.add_argument("--tokens", default=os.getenv("OP_TOKENS_JSON", "wpr_agent/config/op_oauth_tokens.json"))
    args = ap.parse_args()

    if not all([args.auth_url, args.token_url, args.client_id, args.client_secret, args.redirect_uri]):
        print(json.dumps({"error": "Missing OAuth env/args"}, indent=2))
        return

    host, port, path = _parse_redirect(args.redirect_uri)
    # start local server in a thread
    t = threading.Thread(target=_serve_one, args=(host, port), daemon=True)
    t.start()

    # open auth URL
    params = {
        "client_id": args.client_id,
        "redirect_uri": args.redirect_uri,
        "response_type": "code",
        "scope": args.scopes,
    }
    sep = '&' if '?' in (args.auth_url or '') else '?'
    auth_link = f"{args.auth_url}{sep}{urllib.parse.urlencode(params)}"
    try:
        webbrowser.open(auth_link)
    except Exception:
        pass
    print("Authorize in your browser:")
    print(auth_link)

    # wait for code capture (up to ~5 minutes via server loop)
    t.join(timeout=310)
    code = _Handler.code_holder.get("code")
    if not code:
        print(json.dumps({"error": "Code not captured (timeout)"}, indent=2))
        return

    # exchange code for tokens
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
        return

    data = r.json() or {}
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    Path(args.tokens).parent.mkdir(parents=True, exist_ok=True)
    Path(args.tokens).write_text(json.dumps({"access_token": access_token, "refresh_token": refresh_token}, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "tokens_file": args.tokens}, indent=2))


if __name__ == "__main__":
    main()

