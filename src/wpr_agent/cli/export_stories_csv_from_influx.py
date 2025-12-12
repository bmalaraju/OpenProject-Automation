from __future__ import annotations

"""
Generate Stories CSV per project after Epics are imported.

This script resolves Epic IDs from OpenProject by matching Subject (ProjectName :: WPR Order ID),
then expands each Influx row by WP Quantity to one Story per instance, writing Parent (epic ID).

Usage:
  python wpr_agent/scripts/export_stories_csv_from_influx.py --since 7d --registry wpr_agent/config/product_project_registry.json --out-dir artifacts/csv
  python wpr_agent/scripts/export_stories_csv_from_influx.py --batch-id 20251104232022 --registry wpr_agent/config/product_project_registry.json --out-dir artifacts/csv
"""

import argparse
import csv
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
load_dotenv(BASE / ".env", override=False)

from wpr_agent.router.tools.influx_source import read_influx_df_tool  # type: ignore
from wpr_agent.router.tools.registry import load_product_registry_tool  # type: ignore
from wp_jira_agent.openproject import OpenProjectClient  # type: ignore
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None


def _build_subject(project_name: str, order_id: str) -> str:
    pn = (project_name or "").strip()
    oid = (order_id or "").strip()
    if pn and oid:
        return f"{pn} :: {oid}"
    return oid or pn or "Work Package"


def _story_summary(order_id: str, instance: int, name: str) -> str:
    oid = (order_id or "").strip()
    nm = (name or "").strip()
    if oid and instance:
        return f"{oid}-{instance} | {nm}" if nm else f"{oid}-{instance}"
    return nm or oid


def _epic_id_map(client: OpenProjectClient, project_key: str) -> Dict[str, str]:
    # Return subject -> id for epics in project
    pid = None
    try:
        obj = client.resolve_project(project_key)
        pid = str(obj.get("id") or "") if obj else None
    except Exception:
        pid = None
    if not pid:
        return {}
    # Fetch all work packages of type Epic in project, collect id and subject
    filters = [
        {"project": {"operator": "=", "values": [pid]}},
        {"type": {"operator": "=", "values": [str((client.list_types_for_project(pid) or {}).get('epic', {}).get('id') or '')]}},
    ]
    # If type resolution fails, fallback to scanning all and filtering by embedded type name
    items = client.search_work_packages(filters, page_size=1000)
    out: Dict[str, str] = {}
    for it in items or []:
        try:
            sid = str(it.get("id") or "").strip()
            subj = str(it.get("subject") or "").strip()
            if sid and subj:
                out[subj] = sid
        except Exception:
            continue
    return out


def export_stories(since: Optional[str], batch_id: Optional[str], registry_path: str, out_dir: Path) -> List[str]:
    tracer = get_tracer()
    span = None
    try:
        if tracer:
            span = tracer.start_trace("script.export_stories_csv_from_influx", input={"since": since or "", "batch_id": batch_id or "", "out_dir": str(out_dir)})
    except Exception:
        span = None
    df = read_influx_df_tool(since=since if not batch_id else None, batch_id=batch_id)
    if df is None or len(df) == 0:
        try:
            if span:
                span.set_attribute("rows", 0)
                span.end()
        except Exception:
            pass
        return []
    reg = load_product_registry_tool(registry_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = OpenProjectClient()
    written: List[str] = []
    for product, sub in df.groupby("Product"):
        project_key = reg.get(str(product).strip())
        if not project_key:
            continue
        subj_to_id = _epic_id_map(client, project_key)
        if not subj_to_id:
            continue
        rows: List[Dict[str, str]] = []
        for _, r in sub.iterrows():
            subject = _build_subject(str(r.get("Project Name", "")), str(r.get("WP Order ID", "")))
            epic_id = subj_to_id.get(subject)
            if not epic_id:
                continue
            try:
                qty = int(float(str(r.get("WP Quantity", 0) or 0)))
            except Exception:
                qty = 0
            if qty <= 0:
                qty = 1
            for i in range(1, qty + 1):
                rows.append(
                    {
                        "Subject": _story_summary(str(r.get("WP Order ID", "")), i, str(r.get("WP Name", ""))),
                        "Type": "Story",
                        "Parent": epic_id,
                        "DueDate": str(r.get("WP Requested Delivery Date", "")) or str(r.get("WP Readiness Date", "")) or str(r.get("Approved Date", "")),
                        "ExternalKey": str(r.get("WP Order ID", "")),
                    }
                )
        if not rows:
            continue
        path = out_dir / f"stories_{project_key}.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["Subject", "Type", "Parent", "DueDate", "ExternalKey"])
            w.writeheader()
            for row in rows:
                w.writerow(row)
        written.append(str(path))
    try:
        if span:
            span.set_attribute("files", len(written))
            span.end()
    except Exception:
        pass
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Export Stories CSV per project after Epic import")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--since")
    src.add_argument("--batch-id")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out = export_stories(args.since, args.batch_id, args.registry, Path(args.out_dir))
    if not out:
        print("no_rows: nothing exported")
    else:
        print("exported:")
        for p in out:
            print(p)


if __name__ == "__main__":
    main()
