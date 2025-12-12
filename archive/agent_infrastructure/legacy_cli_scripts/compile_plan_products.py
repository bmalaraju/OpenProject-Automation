from __future__ import annotations

"""
Compile PlanBundle(s) using Product→Project routing, Epic per WPR Order ID,
and Story instances per WP Quantity.

Outputs a bundles JSON compatible with apply_plan.py.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wpr_agent.models import PlanBundle, ProductPlan, AnnotatedIssuePlan, JiraIssuePlan
from wpr_agent.tools.excel_tools import ensure_columns, story_description_adf, epic_description_adf
from wpr_agent.services.provider import make_service  # type: ignore


def load_product_registry(path: Path) -> Dict[str, str]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        obj = {"registry": {}}
    reg = obj.get("registry") or {}
    return {str(k): str(v) for k, v in reg.items()}


def _to_iso(value: Any) -> str:
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=False)
        if pd.isna(ts):
            return ""
        # Return date-only when no time component
        try:
            if int(ts.hour) or int(ts.minute) or int(ts.second):
                return ts.isoformat()
        except Exception:
            pass
        return ts.date().isoformat()
    except Exception:
        return str(value or "")


def main() -> None:
    ap = argparse.ArgumentParser(description="Compile bundles per Product: Epic=Order ID, Stories=Quantity.")
    ap.add_argument("--file", "-f", required=True)
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--registry", default=str(BASE_DIR / "config" / "product_project_registry.json"))
    ap.add_argument("--output", "-o", default="artifacts/bundles_products.json")
    args = ap.parse_args()

    try:
        df = pd.read_excel(args.file, sheet_name=args.sheet, engine="openpyxl").fillna("")
    except Exception as ex:
        print(json.dumps({"error": f"Failed to read Excel: {ex}"}, indent=2))
        raise SystemExit(1)

    df = ensure_columns(df)
    reg = load_product_registry(Path(args.registry))

    # Group by Product -> Order ID
    bundles: List[PlanBundle] = []
    svc = make_service()
    fieldmaps: Dict[str, Any] = {}
    for prod, prod_df in df.groupby("Product", dropna=False):
        product = str(prod or "").strip() or "Default"
        project_key = reg.get(product, reg.get("Default", ""))
        if not project_key:
            # Skip if no mapping
            # In a full implementation, collect warnings per bundle
            continue

        bundle = PlanBundle(domain=product, project_key=project_key)
        # Discover fieldmap for this project once
        if project_key not in fieldmaps:
            try:
                fieldmaps[project_key] = svc.discover_fieldmap(project_key)
            except Exception:
                fieldmaps[project_key] = None
        fmap = fieldmaps.get(project_key)
        lowmap = {}
        if fmap and getattr(fmap, "discovered_custom_fields", None):
            lowmap = {str(k).strip().lower(): v for k, v in fmap.discovered_custom_fields.items()}

        def fid(name: str) -> str | None:
            return lowmap.get(name.strip().lower()) if lowmap else None
        for order, sub in prod_df.groupby("WP Order ID", dropna=False):
            order_id = str(order or "").strip()
            if not order_id:
                continue
            # Use the last row for description context
            row0 = {k: str(v or "") for k, v in dict(sub.iloc[-1]).items()}
            meta = {
                "project_name": str(row0.get("Project Name", "") or ""),
                "product": product,
                "domain": str(row0.get("Domain", "") or row0.get("Domain1", "") or ""),
                "customer": str(row0.get("Customer", "") or ""),
            }
            epic_summary = f"{product} :: {order_id}"
            epic_desc = epic_description_adf(meta)
            # Build Epic fields from known WPR field names present on Epic screens
            epic_fields: Dict[str, Any] = {}
            # High-level context
            if fid("WPR Product"):
                epic_fields[fid("WPR Product")] = product
            if fid("WPR Project"):
                epic_fields[fid("WPR Project")] = row0.get("Project Name", "")
            dom_val = str(row0.get("Domain", "") or row0.get("Domain1", "") or "")
            if fid("WPR Domain"):
                epic_fields[fid("WPR Domain")] = dom_val
            if fid("WPR Customer"):
                epic_fields[fid("WPR Customer")] = row0.get("Customer", "")
            # Identity + core
            if fid("WPR BP ID"):
                epic_fields[fid("WPR BP ID")] = row0.get("BP ID", "")
            if fid("WPR WP Order ID") or fid("WPR WP order id"):
                epic_fields[fid("WPR WP Order ID") or fid("WPR WP order id")] = order_id
            if fid("WPR WP ID"):
                epic_fields[fid("WPR WP ID")] = row0.get("WP ID", "")
            # Quantity
            # Build stories by quantity (take the max quantity across rows for safety)
            try:
                qty_val = int(max(1, int(pd.to_numeric(sub["WP Quantity"], errors="coerce").fillna(0).max())))
            except Exception:
                qty_val = 1
            if fid("WPR WP Quantity"):
                epic_fields[fid("WPR WP Quantity")] = qty_val
            # Dates and status on Epic
            mapping_dates = [
                ("WPR Acknowledgement Date", "Acknowledgement Date"),
                ("WPR Added Date", "Added Date"),
                ("WPR Approved Date", "Approved Date"),
                ("WPR Cancelled Date", "Cancelled Date"),
                ("WPR PO End Date", "PO EndDate"),
                ("WPR PO Start Date", "PO StartDate"),
                ("WPR Readiness Date", "WP Readiness Date"),
                ("WPR Requested Date", "WP Requested Delivery Date"),
                ("WPR Submitted Date", "Submitted Date"),
                ("WPR Updated Date", "Updated Date"),
                ("WPR Start Date", "Acknowledgement Date"),  # derived start
            ]
            for disp, col in mapping_dates:
                f = fid(disp)
                if f:
                    val = _to_iso(row0.get(col, ""))
                    if val:
                        epic_fields[f] = val
            # Status, STD, Employee Name, WP Name, Order Status
            # Normalize and wrap select option for WPR WP Order Status
            status_field = fid("WPR WP Order Status")
            if status_field:
                raw_status = str(row0.get("WP Order Status", "") or "").strip().lower()
                norm_map = {
                    "pending acknowledgement": "Pending Acknowledgement",
                    "pending acknowledgment": "Pending Acknowledgement",
                    "acknowledge": "Acknowledged",
                    "acknowledged": "Acknowledged",
                    "pending approval": "Pending Approval",
                    "approved": "Approved",
                    "objected": "Objected",
                    "rejected": "Rejected",
                    "cancelled": "Cancelled",
                    "canceled": "Cancelled",
                    "waiting for order submission": "Waiting for order submission",
                }
                canon = norm_map.get(raw_status)
                if canon:
                    # Use value form; alternatively resolve option id via API and set {"id": "..."}
                    epic_fields[status_field] = {"value": canon}
            if fid("WPR STD"):
                try:
                    epic_fields[fid("WPR STD")] = int(pd.to_numeric(row0.get("STD", 0), errors="coerce"))
                except Exception:
                    pass
            if fid("WPR Employee Name"):
                epic_fields[fid("WPR Employee Name")] = row0.get("Employee Name", "")
            if fid("WPR WP Name"):
                epic_fields[fid("WPR WP Name")] = row0.get("WP Name", "")
            # Epic Due date (system): map from 'WP Requested Delivery Date' (date-only)
            try:
                d_ep = _to_iso(row0.get("WP Requested Delivery Date", ""))
                if d_ep:
                    epic_fields["duedate"] = d_ep.split("T", 1)[0]
            except Exception:
                pass

            epic_plan = JiraIssuePlan(
                issue_type="Epic",
                project_key=project_key,
                summary=epic_summary,
                description_adf=epic_desc,
                fields=epic_fields,
                parent_key=None,
            )
            epic_ann = AnnotatedIssuePlan(
                plan=epic_plan,
                natural_key=f"EPIC::{project_key}::{order_id}",
                identity={"field_name": "WPR WP order id", "value": order_id},
                link_intent=None,
            )

            # qty already computed above as qty_val

            # Use last row for core fields in description
            row_dict: Dict[str, Any] = {k: row0.get(k, "") for k in row0.keys()}
            st_desc = story_description_adf(row_dict)
            # For now, story names should be '<ORDER_ID>-<n>' sequential labels
            stories: List[AnnotatedIssuePlan] = []
            for i in range(1, qty_val + 1):
                st_summary = f"{order_id}-{i}"
                # Story fields mapping (screen shows WPR BP ID, WPR WP ID, WPR WP Name)
                story_fields: Dict[str, Any] = {}
                if fid("WPR BP ID"):
                    story_fields[fid("WPR BP ID")] = row0.get("BP ID", "")
                if fid("WPR WP ID"):
                    story_fields[fid("WPR WP ID")] = row0.get("WP ID", "")
                if fid("WPR WP Name"):
                    story_fields[fid("WPR WP Name")] = row0.get("WP Name", "")
                # Map Jira 'duedate' from 'WP Requested Delivery Date' (date-only)
                try:
                    dval = _to_iso(row0.get("WP Requested Delivery Date", ""))
                    if dval:
                        story_fields["duedate"] = dval.split("T", 1)[0]
                except Exception:
                    pass
                # Ensure canonical order id is written to story identity field when present on screens
                if fid("WPR WP Order ID"):
                    story_fields[fid("WPR WP Order ID")] = order_id

                st_plan = JiraIssuePlan(
                    issue_type="Story",
                    project_key=project_key,
                    summary=st_summary,
                    description_adf=st_desc,
                    fields=story_fields,
                    parent_key=None,
                )
                stories.append(
                    AnnotatedIssuePlan(
                        plan=st_plan,
                        natural_key=f"STORY::{project_key}::{order_id}#{i}",
                        # Per-instance identity to satisfy within-order uniqueness; field mapping uses base order_id
                        identity={"field_name": "WPR WP order id", "value": f"{order_id}#{i}"},
                        link_intent={"epic_ref": f"EPIC::{project_key}::{order_id}"},
                    )
                )

            bundle.product_plans.append(ProductPlan(bp_id=order_id, epic=epic_ann, stories=stories, warnings=[]))
        bundles.append(bundle)

    out = {"bundles": [b.model_dump() for b in bundles]}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "bundles": len(bundles), "output": args.output}, indent=2))


if __name__ == "__main__":
    main()
