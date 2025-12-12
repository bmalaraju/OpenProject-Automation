from __future__ import annotations

"""
Ensure OpenProject subprojects exist under a parent project for all product→project mappings.

Usage:
  python wpr_agent/scripts/ensure_subprojects.py --registry wpr_agent/config/product_project_registry.json --parent Nokia --apply

Env:
  - OPENPROJECT_BASE_URL, OPENPROJECT_USERNAME=apikey, OPENPROJECT_API_KEY=<token>
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

from wpr_agent.router.tools.registry import load_product_registry_tool
from wp_jira_agent.openproject import OpenProjectClient


def normalize_identifier(key: str) -> str:
    return (key or "").strip().lower().replace(" ", "-")


def main() -> None:
    ap = argparse.ArgumentParser(description="Ensure OP subprojects exist for product registry")
    ap.add_argument("--registry", required=True, help="Product→Project registry JSON path")
    ap.add_argument("--parent", required=False, help="Parent project identifier or name (defaults to OPENPROJECT_PARENT_PROJECT)")
    ap.add_argument("--apply", action="store_true", help="Create missing subprojects (otherwise dry-run)")
    args = ap.parse_args()

    parent = args.parent or os.getenv("OPENPROJECT_PARENT_PROJECT") or ""
    if not parent:
        print(json.dumps({"error": "Parent project not specified (set --parent or OPENPROJECT_PARENT_PROJECT)"}, indent=2))
        raise SystemExit(1)

    reg = load_product_registry_tool(args.registry)
    wanted: List[str] = sorted(set(reg.values()))

    client = OpenProjectClient()
    # Resolve parent
    parent_obj = client._find_project_by_identifier_or_name(parent)
    if not parent_obj:
        print(json.dumps({"error": f"Parent project '{parent}' not found"}, indent=2))
        raise SystemExit(2)
    pid = str(parent_obj.get("id"))

    # Index existing children under parent
    existing = []
    for pr in client.list_projects():
        try:
            ph = (((pr.get("_links") or {}).get("parent") or {}).get("href"))
            if isinstance(ph, str) and ph.rstrip("/").endswith(f"/projects/{pid}"):
                existing.append(str(pr.get("identifier") or ""))
        except Exception:
            continue

    created: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    for key in wanted:
        ident = normalize_identifier(key)
        if ident in existing:
            skipped.append(ident)
            continue
        if not args.apply:
            print(f"dry-run: would create subproject '{ident}' under '{parent}'")
            continue
        # Create
        name = key
        status, body = client.create_project(name=name, identifier=ident, parent_id=pid)
        if status in (200, 201):
            created.append(ident)
        else:
            errors.append(f"{ident}: {body}")

    out = {"parent": parent, "created": created, "skipped": skipped, "errors": errors}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

