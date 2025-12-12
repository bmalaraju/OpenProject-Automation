from __future__ import annotations

"""
Product compile tool for the Router: Epic per WPR WP order id, Stories per quantity.

This mirrors the script-based product compiler at a high level, but is kept
lightweight for router usage.
"""

from typing import Any, Dict, List
import os

import pandas as pd

from wpr_agent.models import TrackerFieldMap, PlanBundle, ProductPlan, AnnotatedIssuePlan, IssuePlan

# Local implementation of description generators (replacing missing wpr_agent.tools.excel_tools)
def epic_description_adf(row: Dict[str, Any]) -> Dict[str, Any]:
    """Generate ADF/JSON description for Epic from row data."""
    # Simple text representation of key fields
    lines = []
    for k, v in row.items():
        if v and str(v).strip():
            lines.append(f"**{k}**: {v}")
    
    text = "\n".join(lines)
    
    # Return OpenProject/Jira compatible ADF structure
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}]
            }
        ]
    }

def story_description_adf(row: Dict[str, Any]) -> Dict[str, Any]:
    """Generate ADF/JSON description for Story from row data."""
    return epic_description_adf(row)  # Reuse same format



def _to_iso(value: Any) -> str:
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=False)
        if pd.isna(ts):
            return ""
        try:
            if int(ts.hour) or int(ts.minute) or int(ts.second):
                return ts.isoformat()
        except Exception:
            pass
        return ts.date().isoformat()
    except Exception:
        return str(value or "")


def _lowmap(fmap: TrackerFieldMap | None) -> Dict[str, str]:
    if fmap and getattr(fmap, "discovered_custom_fields", None):
        return {str(k).strip().lower(): v for k, v in fmap.discovered_custom_fields.items()}
    return {}


def _fid(low: Dict[str, str], name: str) -> str | None:
    return low.get(name.strip().lower()) if low else None


def compile_product_bundle_tool(
    product: str,
    project_key: str,
    fieldmap: TrackerFieldMap,
    order_groups: List[tuple[str, pd.DataFrame]],
) -> PlanBundle:
    bundle = PlanBundle(domain=str(product or ""), project_key=project_key)
    low = _lowmap(fieldmap)
    for order_id, sub in order_groups:
        order_id = str(order_id or "").strip()
        if not order_id:
            continue
        
        if order_id in ("WPO00187674", "WPO00187539"):
            print(f"DEBUG: Processing failing order {order_id}")
            print(f"DEBUG: fmap len: {len(low)}")
            print(f"DEBUG: low keys sample: {list(low.keys())[:5]}")
            print(f"DEBUG: sub columns: {list(sub.columns)}")
            print(f"DEBUG: STD column values: {sub['STD'].tolist() if 'STD' in sub.columns else 'MISSING'}")

        # Helper: pick first non-empty across rows for a column
        def first_nonempty(col: str) -> str:
            try:
                series = sub[col]
                for v in series:
                    s = str(v or "").strip()
                    if s:
                        return s
            except Exception:
                pass
            return ""
        # last row retained for description context
        row0 = {k: str(v or "") for k, v in dict(sub.iloc[-1]).items()}
        meta = {
            "project_name": str(row0.get("Project Name", "") or ""),
            "product": product,
            "domain": str(row0.get("Domain", "") or row0.get("Domain1", "") or ""),
            "customer": str(row0.get("Customer", "") or ""),
        }
        epic_summary = f"{product} :: {order_id}"
        epic_desc = epic_description_adf(row0)
        epic_fields: Dict[str, Any] = {}
        # Compute quantity once as integer (max across rows) for consistent numeric field writes
        try:
            qty = int(max(1, int(pd.to_numeric(sub["WP Quantity"], errors="coerce").fillna(0).max())))
        except Exception:
            qty = 1
        # Identity + context (best-effort; only when fields discovered)
        prov = "openproject"
        # Direct mapping for selected Epic fields from row0 (no cross-row aggregation)
        try:
            q_epic = int(pd.to_numeric(row0.get("WP Quantity", 0), errors="coerce")) if str(row0.get("WP Quantity", "")).strip() != "" else None
        except Exception:
            q_epic = None
        domain_val = row0.get("Domain", "") or row0.get("Domain1", "")
        # Prefer first non-empty across rows for key epic fields to avoid blanks from a sparse last row
        proj_name_val = first_nonempty("Project Name") or row0.get("Project Name", "")
        customer_val = first_nonempty("Customer") or row0.get("Customer", "")
        wp_id_val = first_nonempty("WP ID") or row0.get("WP ID", "")
        wp_name_val = first_nonempty("WP Name") or row0.get("WP Name", "")
        status_val = first_nonempty("WP Order Status") or row0.get("WP Order Status", "")
        for disp, val in (
            ("WPR Product", product),
            ("WPR Project", proj_name_val),
            ("WPR Domain", domain_val),
            ("WPR Customer", customer_val),
            ("WPR BP ID", row0.get("BP ID", "")),
            ("WPR WP Order ID", order_id),
            ("WPR WP ID", wp_id_val),
            ("WPR WP Name", wp_name_val),
            ("WPR WP Quantity", q_epic if q_epic is not None else ""),
            ("WPR WP Order Status", status_val),
        ):
            f = _fid(low, disp)
            if f and val not in (None, ""):
                # Jira select-type fields require option objects {"value": "..."}; OpenProject accepts plain text
                if disp.lower() == "wpr wp order status" and prov == "jira":
                    raw = str(val).strip().lower()
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
                    canon = norm_map.get(raw)
                    if canon:
                        epic_fields[f] = {"value": canon}
                    # else: skip setting invalid status to avoid Jira validation error
                else:
                    epic_fields[f] = val

        # Include Employee Name and STD on Epic (direct values per order, no concatenation/aggregation)
        try:
            f_emp = _fid(low, "WPR Employee Name")
            if f_emp:
                # pick first non-empty across rows for this order
                emp_val = first_nonempty("Employee Name")
                if emp_val:
                    epic_fields[f_emp] = emp_val
        except Exception:
            pass
        try:
            f_std = _fid(low, "WPR STD")
            if f_std:
                std_val = None
                try:
                    # first numeric STD across rows
                    series = sub["STD"]
                    for v in series:
                        try:
                            num = float(pd.to_numeric(v, errors="coerce"))
                            if not pd.isna(num):
                                std_val = float(num)
                                break
                        except Exception:
                            continue
                except Exception:
                    std_val = None
                if std_val is None:
                    try:
                        num = float(pd.to_numeric(row0.get("STD", 0), errors="coerce"))
                        if not pd.isna(num):
                            std_val = float(num)
                    except Exception:
                        std_val = None
                if std_val is not None:
                    epic_fields[f_std] = std_val
        except Exception:
            pass
        # Epic duedate: map from 'WP Readiness Date' (date-only)
        try:
            # prefer first non-empty Readiness across rows
            rd = ""
            try:
                for v in sub["WP Readiness Date"]:
                    iso = _to_iso(v)
                    if iso:
                        rd = iso
                        break
            except Exception:
                rd = _to_iso(row0.get("WP Readiness Date", ""))
            if rd:
                epic_fields["duedate"] = rd.split("T", 1)[0]
        except Exception:
            pass
        # Dates (ISO)
        date_pairs = [
            ("WPR Acknowledgement Date", "Acknowledgement Date"),
            ("WPR Added Date", "Added Date"),
            ("WPR Approved Date", "Approved Date"),
            ("WPR Cancelled Date", "Cancelled Date"),
            ("WPR PO End Date", "PO EndDate"),
            ("WPR PO Start Date", "PO StartDate"),
            ("WPR Readiness Date", "WP Readiness Date"),
            ("WPR Requested Date", "WP Requested Delivery Date"),
            ("WPR Submitted Date", "Submitted Date"),
            # "WPR Updated Date" moved to special handling below
            ("WPR Start Date", "Acknowledgement Date"),
        ]
        for disp, col in date_pairs:
            f = _fid(low, disp)
            if f:
                val = ""
                try:
                    # scan first non-empty date across rows
                    vals = sub[col]
                    for v in vals:
                        iso = _to_iso(v)
                        if iso:
                            val = iso
                            break
                except Exception:
                    val = _to_iso(row0.get(col, ""))
                if val:
                    epic_fields[f] = val
        
        # Special handling for Updated Date (force date-only to avoid unnecessary diffs/failures)
        f_upd = _fid(low, "WPR Updated Date")
        if f_upd:
            val = ""
            try:
                vals = sub["Updated Date"]
                for v in vals:
                    iso = _to_iso(v)
                    if iso:
                        val = iso.split("T")[0] # Force date-only
                        break
            except Exception:
                pass
            if not val:
                 iso = _to_iso(row0.get("Updated Date", ""))
                 if iso:
                     val = iso.split("T")[0]
            if val:
                epic_fields[f_upd] = val
        
        if order_id in ("WPO00187674", "WPO00187539"):
            print(f"DEBUG: epic_fields keys: {list(epic_fields.keys())}")
            print(f"DEBUG: customField2 (Order ID): {epic_fields.get(low.get('wpr wp order id'))}")
            print(f"DEBUG: customField23 (STD): {epic_fields.get(low.get('wpr std'))}")

        # Build epic plan
        epic_plan = IssuePlan(
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
        # Story instances (use computed qty)
        row_dict: Dict[str, Any] = {k: row0.get(k, "") for k in row0.keys()}
        st_desc = story_description_adf(row_dict)
        stories: List[AnnotatedIssuePlan] = []
        for i in range(1, qty + 1):
            st_summary = f"{order_id}-{i}"
            st_fields: Dict[str, Any] = {}
            # Story identity fields (limited set): WPR WP ID, WPR WP Name
            for disp, col in (
                ("WPR WP ID", "WP ID"),
                ("WPR WP Name", "WP Name"),
            ):
                f = _fid(low, disp)
                if f:
                    # Prefer first non-empty across rows for story identity fields
                    val = first_nonempty(col) or row0.get(col, "")
                    if val:
                        st_fields[f] = val
            # Skip Story status field per updated requirement unless explicitly enabled
            # Enable via env STORY_STATUS_ENABLED=1 if needed
            from os import getenv as _getenv
            story_status_enabled = str(_getenv("STORY_STATUS_ENABLED", "0")).strip() == "1"
            if story_status_enabled:
                # Order status: canonical text for OP, Jira requires object
                f_status = _fid(low, "WPR WP Order Status")
                if f_status and first_nonempty("WP Order Status"):
                    raw = first_nonempty("WP Order Status").strip().lower()
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
                    canon = norm_map.get(raw, first_nonempty("WP Order Status"))
                    if prov == "jira":
                        st_fields[f_status] = {"value": canon}
                    else:
                        st_fields[f_status] = canon
            # Due date: map from 'WP Readiness Date' (YYYY-MM-DD)
            try:
                rd = ""
                try:
                    for v in sub["WP Readiness Date"]:
                        iso = _to_iso(v)
                        if iso:
                            rd = iso
                            break
                except Exception:
                    rd = _to_iso(row0.get("WP Readiness Date", ""))
                if rd:
                    st_fields["duedate"] = rd.split("T", 1)[0]
            except Exception:
                pass
            # Ensure canonical story identity field is set to base order_id if available on Story screens
            f_order = _fid(low, "WPR WP Order ID") or _fid(low, "WPR WP order id")
            if f_order and order_id:
                st_fields[f_order] = order_id
            # Skip start date mapping per updated spec
            st_plan = IssuePlan(
                issue_type="Story",
                project_key=project_key,
                summary=st_summary,
                description_adf=st_desc,
                fields=st_fields,
                parent_key=None,
            )
            stories.append(
                AnnotatedIssuePlan(
                    plan=st_plan,
                    natural_key=f"STORY::{project_key}::{order_id}#{i}",
                    # Use per-instance identity to satisfy within-order uniqueness
                    identity={"field_name": "WPR WP order id", "value": f"{order_id}#{i}"},
                    link_intent={"epic_ref": f"EPIC::{project_key}::{order_id}"},
                )
            )
        bundle.product_plans.append(ProductPlan(bp_id=order_id, epic=epic_ann, stories=stories, warnings=[]))
    return bundle
