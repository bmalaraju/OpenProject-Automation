from __future__ import annotations

"""
In-process OpenProject apply runner.

Reads a product-based bundles JSON and applies changes using OpenProjectServiceV2
directly (bypassing shell env propagation issues). Finds/creates Epics and Stories
with correct type IDs (Epic/User story), links Story→Epic, and prints a concise
result JSON with created/updated keys and any errors.

Usage:
  python wpr_agent/scripts/apply_with_service.py --bundles artifacts/bundles.json

Env requirements (Basic auth recommended for now):
  - TRACKER_PROVIDER=openproject
  - WP_OP_CONFIG_PATH=wpr_agent/config/basic_openproject_config.json
  - OPENPROJECT_PARENT_PROJECT=Nokia
  - OPENPROJECT_USERNAME=apikey
  - OPENPROJECT_API_KEY=<token>
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv


def _load_json(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as ex:
        raise SystemExit(f"Failed to read {p}: {ex}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply product bundles via OpenProject service (in-process)")
    ap.add_argument("--bundles", required=True)
    args = ap.parse_args()

    # Bootstrap env (prefers repo .env)
    BASE_DIR = Path(__file__).resolve().parents[1]
    # Ensure repo root and wpr_agent are importable
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    ROOT = BASE_DIR.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(BASE_DIR / ".env", override=False)

    # Force provider to openproject unless caller already set it
    os.environ.setdefault("TRACKER_PROVIDER", "openproject")
    # Default to Basic config if caller did not set one
    os.environ.setdefault("WP_OP_CONFIG_PATH", str(BASE_DIR / "config" / "basic_openproject_config.json"))
    os.environ.setdefault("OPENPROJECT_PARENT_PROJECT", os.getenv("OPENPROJECT_PARENT_PROJECT", "Nokia"))

    # Late import to pick env
    from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2  # type: ignore

    svc = OpenProjectServiceV2()

    bundle_path = Path(args.bundles)
    data = _load_json(bundle_path)

    created: List[str] = []
    updated: List[str] = []
    errors: List[str] = []

    bundles: List[Dict[str, Any]] = data.get("bundles") or []
    for b in bundles:
        project_key = b.get("project_key") or ""
        if not project_key:
            continue
        # Discover per project (types, custom fields)
        try:
            fmap = svc.discover_fieldmap(project_key)
        except Exception:
            fmap = None
        for plan in b.get("product_plans") or []:
            bp_id = plan.get("bp_id") or ""
            epic_ann = plan.get("epic") or {}
            epp = epic_ann.get("plan") or {}
            ep_summary = epp.get("summary") or ""
            # Upsert Epic: identity (order id) preferred, then summary
            ex = None
            try:
                ex = svc.find_epic_by_order_id(project_key, bp_id, fmap=fmap) if bp_id else None
            except Exception:
                ex = None
            if not ex:
                try:
                    ex = svc.find_epic_by_summary(project_key, ep_summary)
                except Exception:
                    ex = None
            if ex:
                epic_key = ex.get("key")
                fields = svc.build_epic_fields(project_key, ep_summary, epp.get("description_adf") or {})
                try:
                    fields.update(epp.get("fields") or {})
                except Exception:
                    pass
                diff = svc.compute_epic_diff(fields, ex.get("fields") or {})
                if diff:
                    ok, res, _, _ = svc.update_issue_resilient(epic_key, diff)
                    if ok:
                        updated.append(epic_key)
                    else:
                        errors.append(f"Epic update failed ({ep_summary}): {res}")
            else:
                fields = svc.build_epic_fields(project_key, ep_summary, epp.get("description_adf") or {})
                try:
                    fields.update(epp.get("fields") or {})
                except Exception:
                    pass
                ok, res, _, _ = svc.create_issue_resilient(fields)
                if ok:
                    epic_key = res.get("key")
                    created.append(epic_key)
                else:
                    errors.append(f"Epic create failed ({bp_id}): {res}")
                    continue
            # Ensure epic_key present
            if not ex and not locals().get("epic_key"):
                continue
            if ex:
                epic_key = ex.get("key")
            # Upsert Stories
            for st_ann in plan.get("stories") or []:
                stp = st_ann.get("plan") or {}
                st_summary = stp.get("summary") or ""
                # Prefer exact summary lookup (instance-safe)
                try:
                    sx = svc.find_story_by_summary(project_key, st_summary)
                except Exception:
                    sx = None
                # Build planned story fields and merge record values
                due = (stp.get("fields") or {}).get("duedate")
                planned = svc.build_story_fields(
                    project_key,
                    summary=st_summary,
                    description_adf=stp.get("description_adf") or {},
                    due_date=due,
                    assignee_account_id=None,
                    epic_key=epic_key,
                )
                try:
                    extras = stp.get("fields") or {}
                    if extras:
                        planned.update(extras)
                except Exception:
                    pass
                if sx:
                    diff = svc.compute_story_diff(planned, sx.get("fields") or {})
                    if diff:
                        ok2, res2, _, _ = svc.update_issue_resilient(sx.get("key"), diff)
                        if ok2:
                            updated.append(sx.get("key"))
                        else:
                            errors.append(f"Story update failed ({sx.get('key')}): {res2}")
                else:
                    ok2, res2, _, _ = svc.create_issue_resilient(planned)
                    if ok2:
                        created.append(res2.get("key"))
                    else:
                        errors.append(f"Story create failed '{st_summary}': {res2}")

    out = {
        "created": [k for k in created if k],
        "updated": [k for k in updated if k],
        "errors": errors,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
