from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Bootstrap env and paths
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wpr_agent.models import PlanBundle
from wpr_agent.validator.plan_validate import validate_bundles

try:
    # Optional; used only when --online passed
    from wpr_agent.services.provider import make_service  # type: ignore
except Exception:  # pragma: no cover
    make_service = None  # type: ignore


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate compiled PlanBundles and print a summary.")
    ap.add_argument("--bundles", "-b", default="bundles.json", help="Path to bundles.json emitted by compile_plan.py")
    ap.add_argument("--online", action="store_true", help="Discover Jira fieldmaps per project before validation.")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON summary.")
    ap.add_argument("--full", action="store_true", help="Include per-order errors/warnings in output.")
    args = ap.parse_args()

    p = Path(args.bundles)
    if not p.exists():
        print(json.dumps({"error": f"File not found: {p}"}, indent=2))
        raise SystemExit(1)

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as ex:
        print(json.dumps({"error": f"Failed to read bundles: {ex}"}, indent=2))
        raise SystemExit(1)

    bundle_dicts: List[Dict[str, Any]] = data.get("bundles", []) if isinstance(data, dict) else []
    bundles = [PlanBundle(**bd) for bd in bundle_dicts]

    # Build fieldmaps per project (optional online discovery)
    fieldmaps: Dict[str, Any] = {}
    if args.online and bundles:
        try:
            svc = make_service() if make_service else None
        except Exception:
            svc = None
        if svc is not None:
            for b in bundles:
                if b.project_key and b.project_key not in fieldmaps:
                    try:
                        fieldmaps[b.project_key] = svc.discover_fieldmap(b.project_key)
                    except Exception:
                        fieldmaps[b.project_key] = None

    from wpr_agent.models import JiraFieldMap
    # Normalize None to empty JiraFieldMap
    fieldmaps = {k: (v if v is not None else JiraFieldMap()) for k, v in fieldmaps.items()}

    rep = validate_bundles(bundles, fieldmaps)
    # Summarize per bundle; optionally include per-order detail
    per_bundle = []
    for r in rep.reports:
        err_count = len(r.errors) + sum(len(b.errors) for b in r.product_results)
        warn_count = len(r.warnings) + sum(len(b.warnings) for b in r.product_results)
        bundle_obj: Dict[str, Any] = {
            "domain": r.domain,
            "project_key": r.project_key,
            "ok": r.ok,
            "orders": len(r.product_results),
            "errors": err_count,
            "warnings": warn_count,
        }
        if args.full:
            details = []
            for b in r.product_results:
                details.append({
                    "bp_id": b.bp_id,
                    "ok": b.ok if hasattr(b, 'ok') else (b.epic_ok and b.stories_ok),
                    "epic_ok": b.epic_ok,
                    "stories_ok": b.stories_ok,
                    "errors": list(b.errors),
                    "warnings": list(b.warnings),
                })
            bundle_obj["order_details"] = details
        per_bundle.append(bundle_obj)

    out = {"totals": rep.totals, "bundles": per_bundle}
    if args.pretty:
        print(json.dumps(out, indent=2))
    else:
        print(json.dumps(out))


if __name__ == "__main__":
    main()

