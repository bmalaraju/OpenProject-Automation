from __future__ import annotations

"""
Sanitize artifacts by redacting emails and common secret fields.

Usage:
  python scripts/sanitize_artifacts.py <dir>

Walks the directory and scrubs JSON and text files using the same
redaction rules as the router utils.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TOKEN_KEYS = {
    "authorization",
    "access_token",
    "api_token",
    "token",
    "password",
    "client_secret",
    "client_id",
    "secret",
    "refresh_token",
    "id_token",
    "jwt",
    "private_key",
}


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.strip().lower() in TOKEN_KEYS:
                out[k] = "***REDACTED***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    if isinstance(obj, str):
        return EMAIL_RE.sub("***@***", obj)
    return obj


def process_file(p: Path) -> None:
    try:
        if p.suffix.lower() == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            red = redact(data)
            p.write_text(json.dumps(red, indent=2), encoding="utf-8")
        elif p.suffix.lower() in {".txt", ".log"}:
            txt = p.read_text(encoding="utf-8")
            txt = EMAIL_RE.sub("***@***", txt)
            p.write_text(txt, encoding="utf-8")
    except Exception:
        # Non-fatal: skip malformed or unreadable files
        pass


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python scripts/sanitize_artifacts.py <dir>")
        return 2
    root = Path(argv[1])
    if not root.exists() or not root.is_dir():
        print(f"not_a_dir: {root}")
        return 2
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".json", ".txt", ".log"}:
            process_file(p)
    print(f"sanitized: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

