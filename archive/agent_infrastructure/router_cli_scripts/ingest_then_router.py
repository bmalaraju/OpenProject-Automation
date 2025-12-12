from __future__ import annotations

"""
Ingest latest Excel into Influx, then run the router graph with Influx source (delta-only).

Examples:
  python wpr_agent/scripts/ingest_then_router.py \
    --dir C:\\data\\wpr --pattern "work_packages*.xlsx" --sheet Sheet1 \
    --registry wpr_agent/config/product_project_registry.json --online

  python wpr_agent/scripts/ingest_then_router.py \
    --file work_packages.xlsx --sheet Sheet1 \
    --registry wpr_agent/config/product_project_registry.json --online
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# Bootstrap env and paths (match other scripts)
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Ingest Excel → Influx, then run router graph (influx, delta-only)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file")
    src.add_argument("--dir")
    ap.add_argument("--pattern", default="work_packages*.xlsx")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--continue-on-error", action="store_true")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--backoff-base", type=float, default=0.5)
    ap.add_argument("--artifact-dir")
    ap.add_argument("--report")
    ap.add_argument("--summary")
    return ap.parse_args(argv or sys.argv[1:])


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    # Ingest
    from wpr_agent.cli.upload_excel_to_influx import ingest_file  # type: ignore
    from wpr_agent.serverless.handlers import handle_delta_apply  # type: ignore

    if args.file:
        p = Path(args.file)
        res = ingest_file(p, sheet=str(args.sheet), batch_id=None)
    else:
        # Resolve latest in directory
        d = Path(args.dir)
        cands = sorted(d.glob(args.pattern))
        if not cands:
            print(f"no_files: pattern '{args.pattern}' in {d}")
            return 1
        latest = max(cands, key=lambda p: p.stat().st_mtime)
        res = ingest_file(latest, sheet=str(args.sheet), batch_id=None)

    if res.get("skipped"):
        print(f"ingest_skip: duplicate {res.get('file')} ({res.get('file_hash')})")
    elif not res.get("ok"):
        print(f"ingest_error: {res}")
        return 2
    batch_id = res.get("batch_id")

    # Run router graph with Influx source + delta-only
    payload = {
        "batch_id": batch_id,
        "registry": args.registry,
        "online": bool(args.online),
        "continue_on_error": bool(args.continue_on_error),
        "max_retries": int(args.max_retries),
        "backoff_base": float(args.backoff_base),
        "artifact_dir": args.artifact_dir,
        "report": args.report,
        "summary": args.summary,
    }
    out = handle_delta_apply(payload)
    if not out.get("ok"):
        print(f"router_error: {out}")
        return int(out.get("code", 3))
    print("ok: ingest+router completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
