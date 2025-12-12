from __future__ import annotations

"""
Reconcile OpenProject items to Influx identity store after CSV import.

For each project in registry:
  - Fetch Epics (id, subject) and map to order_id via subject pattern "<ProjectName> :: <OrderID>".
  - Write issue_map Epic mappings (project_key, order_id -> epic key).
  - Optionally: fetch Stories and link to Epics to derive (order_id, instance) -> story key.

Usage:
  python wpr_agent/scripts/reconcile_import_to_influx.py --projects FlowOne,NIAM --write
  python wpr_agent/scripts/reconcile_import_to_influx.py --all --write
"""

import argparse
import os
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from wp_jira_agent.openproject import OpenProjectClient  # type: ignore
from wpr_agent.state.influx_store import InfluxStore  # type: ignore
from wpr_agent.router.tools.registry import load_product_registry_tool  # type: ignore
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None


def _parse_order_id_from_subject(subj: str) -> Optional[str]:
    try:
        if "::" in subj:
            return subj.split("::", 1)[1].strip()
        return subj.split()[0].strip()
    except Exception:
        return None


def reconcile(projects: List[str], registry_path: str, write: bool) -> Dict[str, int]:
    tracer = get_tracer()
    span = None
    try:
        if tracer:
            span = tracer.start_trace("script.reconcile_import_to_influx", input={"projects": len(projects), "write": bool(write)})
    except Exception:
        span = None
    client = OpenProjectClient()
    store = InfluxStore()
    reg = load_product_registry_tool(registry_path)
    res: Dict[str, int] = {"epics": 0, "stories": 0}
    for pkey in projects:
        # Resolve project
        pobj = client.resolve_project(pkey)
        if not pobj:
            continue
        pid = str(pobj.get("id") or "")
        # Fetch Epics
        epics = client.search_work_packages(
            [
                {"project": {"operator": "=", "values": [pid]}},
                {"type": {"operator": "=", "values": [str((client.list_types_for_project(pid) or {}).get('epic', {}).get('id') or '')]}},
            ],
            page_size=1000,
        )
        for e in epics or []:
            try:
                eid = str(e.get("id") or "").strip()
                subj = str(e.get("subject") or "").strip()
                oid = _parse_order_id_from_subject(subj) or ""
                if eid and oid:
                    if write:
                        store.register_epic(pkey, oid, eid)
                    res["epics"] += 1
            except Exception:
                continue
        # Stories reconciliation optional (skipped by default); implement later if needed
    try:
        if span:
            span.set_attribute("epics", int(res.get("epics", 0)))
            span.set_attribute("stories", int(res.get("stories", 0)))
            span.end()
    except Exception:
        pass
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description="Reconcile OP items to Influx identity mappings after CSV import")
    ap.add_argument("--registry", default="wpr_agent/config/product_project_registry.json")
    ap.add_argument("--projects", help="Comma-separated project keys")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--write", action="store_true", help="When set, write mappings; otherwise dry-run")
    args = ap.parse_args()

    load_dotenv(".env", override=False)
    load_dotenv("wpr_agent/.env", override=False)
    reg = load_product_registry_tool(args.registry)
    if args.all:
        pkeys = list(set(reg.values()))
    else:
        pkeys = [x.strip() for x in (args.projects or "").split(",") if x.strip()]
    if not pkeys:
        print("no_projects: provide --projects or --all")
        return
    res = reconcile(pkeys, args.registry, args.write)
    print(f"reconciled: epics={res.get('epics',0)} stories={res.get('stories',0)} write={bool(args.write)}")


if __name__ == "__main__":
    main()
