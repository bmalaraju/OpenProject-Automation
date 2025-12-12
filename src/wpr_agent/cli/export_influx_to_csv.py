from __future__ import annotations

"""
Export Influx input (per project) to CSV files suitable for OpenProject CSV import (Epics).

Usage:
  python wpr_agent/scripts/export_influx_to_csv.py --since 7d --registry wpr_agent/config/product_project_registry.json --out-dir artifacts/csv
  python wpr_agent/scripts/export_influx_to_csv.py --batch-id 20251104232022 --registry wpr_agent/config/product_project_registry.json --out-dir artifacts/csv

Emits one CSV per project key with columns:
  Subject,Type,Description,DueDate,ExternalKey,WPR WP Order Status,ProjectName,Product,Domain,Customer

Notes:
  - ExternalKey holds 'WPR WP Order ID' for post-import reconciliation.
  - Description is markdown extracted from our ADF description builder (one key/value per line).
  - Type is 'Epic' for all rows in this export.
"""

import argparse
import csv
import os
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Bootstrap paths
ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
load_dotenv(BASE / ".env", override=False)

from wpr_agent.router.tools.influx_source import read_influx_df_tool  # type: ignore
from wpr_agent.router.tools.registry import load_product_registry_tool  # type: ignore
from wpr_agent.tools.excel_tools import epic_description_adf, pick_due  # type: ignore
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None


def _adf_to_markdown(adf: Dict) -> str:
    try:
        content = (adf or {}).get("content") or []
        if isinstance(content, list) and content:
            first = content[0] or {}
            para = (first.get("content") or [])
            if isinstance(para, list) and para and isinstance(para[0], dict):
                text = str(para[0].get("text") or "")
                return text
    except Exception:
        pass
    # Fallback: key-value join
    try:
        import json as _json
        return _json.dumps(adf)
    except Exception:
        return ""


def _build_subject(project_name: str, order_id: str) -> str:
    pn = (project_name or "").strip()
    oid = (order_id or "").strip()
    if pn and oid:
        return f"{pn} :: {oid}"
    return oid or pn or "Work Package"


def export_epics(since: Optional[str], batch_id: Optional[str], registry_path: str, out_dir: Path) -> List[str]:
    tracer = get_tracer()
    span = None
    try:
        if tracer:
            span = tracer.start_trace("script.export_influx_to_csv", input={"since": since or "", "batch_id": batch_id or "", "out_dir": str(out_dir)})
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
    # Group by project key via product mapping
    written: List[str] = []
    for product, sub in df.groupby("Product"):
        project_key = reg.get(str(product).strip())
        if not project_key:
            continue
        rows: List[Dict[str, str]] = []
        for _, r in sub.iterrows():
            subject = _build_subject(str(r.get("Project Name", "")), str(r.get("WP Order ID", "")))
            adf = epic_description_adf({k: r.get(k, "") for k in sub.columns})
            desc_md = _adf_to_markdown(adf)
            rows.append(
                {
                    "Subject": subject,
                    "Type": "Epic",
                    "Description": desc_md,
                    "DueDate": pick_due({k: r.get(k, "") for k in sub.columns}),
                    "ExternalKey": str(r.get("WP Order ID", "")),
                    "WPR WP Order Status": str(r.get("WP Order Status", "")),
                    "ProjectName": str(r.get("Project Name", "")),
                    "Product": str(r.get("Product", "")),
                    "Domain": str(r.get("Domain", "") or r.get("Domain1", "")),
                    "Customer": str(r.get("Customer", "")),
                }
            )
        if not rows:
            continue
        path = out_dir / f"epics_{project_key}.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=[
                    "Subject",
                    "Type",
                    "Description",
                    "DueDate",
                    "ExternalKey",
                    "WPR WP Order Status",
                    "ProjectName",
                    "Product",
                    "Domain",
                    "Customer",
                ],
            )
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
    ap = argparse.ArgumentParser(description="Export Influx input to per-project CSVs for Epic import")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--since")
    src.add_argument("--batch-id")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out = export_epics(args.since, args.batch_id, args.registry, Path(args.out_dir))
    if not out:
        print("no_rows: nothing exported")
    else:
        print("exported:")
        for p in out:
            print(p)


if __name__ == "__main__":
    main()
