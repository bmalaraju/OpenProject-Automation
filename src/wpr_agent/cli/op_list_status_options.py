from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser(description="List allowed values for 'WPR WP Order Status' via OP work package form")
    ap.add_argument("--project", required=True, help="Logical project key (e.g., FlowOne)")
    ap.add_argument("--type", default="Epic", choices=["Epic", "Story", "User story"], help="Issuetype to inspect")
    args = ap.parse_args()

    from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2  # type: ignore

    svc = OpenProjectServiceV2()
    pid = svc._project_id(args.project)
    tid = svc._type_id(args.project, "User story" if args.type.lower().startswith("user") else args.type)
    if not pid or not tid:
        print(json.dumps({"error": "Project or type could not be resolved", "project": args.project, "type": args.type}, indent=2))
        raise SystemExit(2)
    status_fid = (svc._cf_map() or {}).get("wpr wp order status")
    if not status_fid:
        print(json.dumps({"error": "Status custom field id not discovered", "project": args.project}, indent=2))
        raise SystemExit(3)
    code, data = svc.client.work_package_form(pid, tid)
    if code != 200:
        print(json.dumps({"error": "Form fetch failed", "status": code, "body": data}, indent=2))
        raise SystemExit(4)
    schema = data.get("schema") or {}
    fmeta: Dict[str, Any] = schema.get(status_fid) or {}
    allowed = None
    try:
        allowed = ((fmeta.get("_links") or {}).get("allowedValues"))
    except Exception:
        allowed = None
    if not allowed:
        allowed = fmeta.get("allowedValues")
    out = []
    if isinstance(allowed, list):
        for opt in allowed:
            try:
                title = str(opt.get("title") or opt.get("name") or "")
                href = ((opt.get("_links") or {}).get("self") or {}).get("href") or opt.get("href")
                out.append({"title": title, "href": href})
            except Exception:
                continue
    print(json.dumps({"project": args.project, "issuetype": args.type, "field_id": status_fid, "allowed": out}, indent=2))


if __name__ == "__main__":
    main()

