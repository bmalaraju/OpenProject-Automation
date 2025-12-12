from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Preflight: Validate OpenProject project configuration and field discovery")
    ap.add_argument("--project", required=True, help="Logical project key (same as Jira key)")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2  # type: ignore
    except Exception as ex:
        print(json.dumps({"ok": False, "error": f"Service import failed: {ex}"}, indent=2))
        raise SystemExit(1)
    svc = OpenProjectServiceV2()
    acc = svc.check_access(args.project)
    fmap = svc.discover_fieldmap(args.project) if acc.get("ok") else None
    out = {
        "project_key": args.project,
        "access": acc,
        "fieldmap": (fmap.model_dump() if hasattr(fmap, "model_dump") else (fmap.dict() if fmap else None)) if fmap is not None else None,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

