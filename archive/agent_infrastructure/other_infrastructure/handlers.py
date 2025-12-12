from __future__ import annotations

"""
Serverless entrypoints for WP-Jira Agent v2.

Exposed handlers (framework-agnostic):
 - handle_ingest_latest(payload: dict | None) -> dict
   Triggers ingestion of the latest Excel from a directory into Influx.

 - handle_op_webhook(payload: dict | None, headers: dict | None) -> dict
   Validates webhook secret and returns an acknowledgement. Intended to be
   extended to trigger a delta apply flow from Influx.

 - handle_cron(payload: dict | None) -> dict
   Placeholder for scheduled triggers (e.g., delta runs).
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional


def handle_ingest_latest(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from wpr_agent.cli.upload_excel_to_influx import ingest_file  # type: ignore

    cfg_dir = (payload or {}).get("dir") or os.getenv("INGEST_SOURCE_DIR")
    pattern = (payload or {}).get("pattern") or os.getenv("INGEST_FILE_PATTERN", "work_packages*.xlsx")
    sheet = (payload or {}).get("sheet") or os.getenv("INGEST_SHEET", "Sheet1")
    batch_id = (payload or {}).get("batch_id") or None
    # Dedupe disabled by design; always ingest
    skip_dup = False
    if not cfg_dir:
        return {"ok": False, "error": "missing INGEST_SOURCE_DIR or payload.dir"}
    d = Path(str(cfg_dir))
    if not d.exists() or not d.is_dir():
        return {"ok": False, "error": f"directory_not_found: {d}"}

    # Find the latest file by mtime
    latest = None
    try:
        cands = sorted(d.glob(str(pattern)))
        latest = max(cands, key=lambda p: p.stat().st_mtime) if cands else None
    except Exception:
        latest = None
    if latest is None:
        return {"ok": False, "error": f"no_files_match: {pattern}"}

    res = ingest_file(latest, sheet=str(sheet), batch_id=(str(batch_id) if batch_id else None), skip_dup=bool(skip_dup))
    return res


def handle_op_webhook(payload: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    secret = os.getenv("OP_WEBHOOK_SECRET")
    provided = None
    try:
        provided = (headers or {}).get("x-op-secret") or (headers or {}).get("X-OP-Secret")
    except Exception:
        provided = None
    if secret and (str(provided or "").strip() != str(secret).strip()):
        return {"ok": False, "status": 401, "error": "invalid_secret"}
    # Placeholder acknowledgement; extend to trigger delta apply
    return {"ok": True, "status": 200}


def handle_cron(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    # Placeholder for scheduled triggers (e.g., delta runs); returns an ack
    return {"ok": True, "status": 200}


def handle_delta_apply(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run router graph with Influx source and delta-only filtering.

    Payload keys (all optional):
      - since: e.g., "12h" (ignored if batch_id provided)
      - batch_id: select a specific ingestion batch
      - registry: path to product→project registry JSON (required)
      - online: bool (default False)
      - continue_on_error: bool (default False)
      - max_retries: int
      - backoff_base: float
      - report, summary, artifact_dir: optional paths
    """
    from wpr_agent.cli import router as router_cli  # type: ignore

    p = payload or {}
    argv: list[str] = [
        "--source", "influx",
        "--registry", str(p.get("registry") or "wpr_agent/config/product_project_registry.json"),
        "--delta-only",
        "--online" if bool(p.get("online")) else "--offline",
        "--dry-run" if not bool(p.get("online")) else "",
    ]
    argv = [a for a in argv if a]
    if p.get("batch_id"):
        argv += ["--batch-id", str(p.get("batch_id"))]
    elif p.get("since"):
        argv += ["--since", str(p.get("since"))]
    if bool(p.get("continue_on_error")):
        argv += ["--continue-on-error"]
    if p.get("max_retries") is not None:
        argv += ["--max-retries", str(int(p.get("max_retries")))]
    if p.get("backoff_base") is not None:
        argv += ["--backoff-base", str(float(p.get("backoff_base")))]
    if p.get("report"):
        argv += ["--report", str(p.get("report"))]
    if p.get("summary"):
        argv += ["--summary", str(p.get("summary"))]
    if p.get("artifact_dir"):
        argv += ["--artifact-dir", str(p.get("artifact_dir"))]
    try:
        router_cli.main(argv)
        return {"ok": True}
    except SystemExit as ex:
        code = int(getattr(ex, "code", 1) or 1)
        return {"ok": code == 0, "code": code}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}
