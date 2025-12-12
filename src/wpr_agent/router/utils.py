"""
Router utilities for Step 11 (Phase 1):
- run_id and timestamp helpers
- redaction helpers for error payloads
- single-line key=value logging helper
"""
from __future__ import annotations

import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict


def gen_run_id() -> str:
    """Generate a unique run identifier combining UTC timestamp and a short UUID.

    Returns
    - str like '2025-09-22T23-25-54Z_ab12cd34'
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{ts}_{str(uuid.uuid4())[:8]}"


def ts_iso_utc() -> str:
    """Return current timestamp in ISO 8601 (UTC)."""
    return datetime.now(timezone.utc).isoformat()


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TOKEN_KEYS = {
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


def redact_error_payload(err: Any) -> Any:
    """Redact sensitive values (emails/tokens) from an error payload.

    Inputs
    - err: arbitrary object (dict/list/str)

    Returns
    - a best-effort redacted clone (strings masked; dict token-like keys masked)
    """
    if isinstance(err, dict):
        out: Dict[str, Any] = {}
        for k, v in err.items():
            if isinstance(k, str) and k.strip().lower() in _TOKEN_KEYS:
                out[k] = "***REDACTED***"
            else:
                out[k] = redact_error_payload(v)
        return out
    if isinstance(err, list):
        return [redact_error_payload(x) for x in err]
    if isinstance(err, str):
        return _EMAIL_RE.sub("***@***", err)
    return err


def log_kv(action: str, **fields: Any) -> None:
    """Print a single-line action log with key=value pairs to stdout.

    Example
    - log_kv("compile_bundle", domain="CLOUD_INFRA", epics=3, stories=12)
    """
    parts = [f"{k}={v}" for k, v in fields.items()]
    line = f"{action}: " + " ".join(parts)
    print(line, file=sys.stdout, flush=True)
