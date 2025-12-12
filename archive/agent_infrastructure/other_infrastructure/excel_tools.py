from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from wpr_agent.models import ExcelRow, WprGroup

RELEVANT_COLUMNS: List[str] = [
    # Identity & grouping
    "BP ID",
    "Project Name",
    "Product",
    "Domain",  # canonical if present
    "Domain1",  # fallback/legacy
    "Customer",
    # Core order fields
    "WP Order ID",
    "WP Order Status",
    "WP ID",
    "WP Name",
    "WP Quantity",
    "Employee Name",
    # Dates and schedule
    "WP Requested Delivery Date",
    "WP Readiness Date",
    "Approved Date",
    "Submitted Date",
    "Cancelled Date",
    "PO StartDate",
    "PO EndDate",
    "Acknowledgement Date",
    "Added Date",
    "Updated Date",
    # Additional epic description fields requested
    "Market",
    "SOW/PA",
    "PO Number",
    "WP Completed Qty",
    "WP Final Quantity",
    "Total Approved Quantity",
    "In-Time Delivery",
    "Customer Region PM",
    "Additional Instruction",
    "Approved/Rejected Reason",
    "Survey Satisfaction Mark",
    "Survey First Right",
    "Survey Suggestion",
    # Metrics
    "STD",
]


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for c in RELEVANT_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    # Prefer canonical Domain; if empty but Domain1 present, copy it
    if "Domain" in df.columns and "Domain1" in df.columns:
        dom = df["Domain"].fillna("").astype(str).str.strip()
        dom1 = df["Domain1"].fillna("").astype(str).str.strip()
        df.loc[dom.eq("") & dom1.ne(""), "Domain"] = df.loc[dom.eq("") & dom1.ne(""), "Domain1"]
    return df[RELEVANT_COLUMNS]


def _to_iso(val: Any) -> str:
    if val is None or str(val).strip() == "":
        return ""
    ts = pd.to_datetime(val, errors="coerce", utc=False)
    if pd.isna(ts):
        return ""
    # prefer date-only when time is empty
    try:
        if int(ts.hour) or int(ts.minute) or int(ts.second):
            return ts.isoformat()
    except Exception:
        pass
    return ts.date().isoformat()


def _to_int(val: Any) -> int:
    try:
        s = str(val).replace(",", "").strip()
        if not s:
            return 0
        return int(float(s))
    except Exception:
        return 0


def pick_due(row: Dict[str, Any]) -> str:
    for k in ("WP Requested Delivery Date", "WP Readiness Date", "Approved Date"):
        d = _to_iso(row.get(k))
        if d:
            return d
    return ""


def group_by_bp(df: pd.DataFrame) -> List[Tuple[Any, pd.DataFrame]]:
    return list(df.groupby("BP ID", dropna=False))


def epic_summary(project_name: str, bp_id: Any) -> str:
    pn = str(project_name or "").strip()
    return f"{pn} :: {bp_id}"


def epic_meta(row0: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "project_name": str(row0.get("Project Name", "") or ""),
        "product": str(row0.get("Product", "") or ""),
        "domain": str(row0.get("Domain", "") or row0.get("Domain1", "") or ""),
        "customer": str(row0.get("Customer", "") or ""),
    }


def story_core(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "wp_order_id": str(row.get("WP Order ID", "") or ""),
        "wp_order_status": str(row.get("WP Order Status", "") or ""),
        "wp_id": str(row.get("WP ID", "") or ""),
        "wp_name": str(row.get("WP Name", "") or ""),
        "wp_qty": _to_int(row.get("WP Quantity", 0)),
        "employee_name": str(row.get("Employee Name", "") or ""),
        "due_date": pick_due(row),
        "submitted_date": _to_iso(row.get("Submitted Date")),
        "cancelled_date": _to_iso(row.get("Cancelled Date")),
        "po_start": _to_iso(row.get("PO StartDate")),
        "po_end": _to_iso(row.get("PO EndDate")),
        "ack_date": _to_iso(row.get("Acknowledgement Date")),
        "added_date": _to_iso(row.get("Added Date")),
        "updated_date": _to_iso(row.get("Updated Date")),
        "approved_date": _to_iso(row.get("Approved Date")),
        "std": _to_int(row.get("STD", 0)),
    }


def story_summary(core: Dict[str, Any]) -> str:
    order = core.get("wp_order_id", "")
    wid = core.get("wp_id", "")
    wname = core.get("wp_name", "")
    if order:
        parts = [order]
        if wid:
            parts.append(wid)
        if wname:
            parts.append(wname)
        return " — ".join(parts)
    if wid and wname:
        return f"{wid} — {wname}"
    return wname or wid or order or "Work Package"


def epic_description_markdown(row: Dict[str, Any]) -> str:
    """Build Epic description as a Markdown key-value list per schema.

    The row dict should contain Excel column names as keys. Missing values are rendered empty.
    """
    keys = [
        "WP Order ID",
        "WP Order Status",
        "Domain",
        "Market",
        "SOW/PA",
        "PO Number",
        "PO StartDate",
        "PO EndDate",
        "Product",
        "WP ID",
        "WP Name",
        "WP Quantity",
        "WP Completed Qty",
        "WP Final Quantity",
        "Total Approved Quantity",
        "WP Requested Delivery Date",
        "WP Readiness Date",
        "In-Time Delivery",
        "Project Name",
        "Customer",
        "Customer Region PM",
        "Additional Instruction",
        "Approved/Rejected Reason",
        "Added Date",
        "Updated Date",
        "Acknowledgement Date",
        "Cancelled Date",
        "Submitted Date",
        "Approved Date",
        "STD",
        "Survey Satisfaction Mark",
        "Survey First Right",
        "Survey Suggestion",
    ]
    lines = [f"- {k}: {str(row.get(k, '') or '')}" for k in keys]
    return "\n".join(lines)


def story_description_markdown(row: Dict[str, Any]) -> str:
    """Build Story description as a Markdown key-value list per schema."""
    keys = [
        "WP Order ID",
        "Product",
        "WP ID",
        "WP Name",
        "WP Requested Delivery Date",
        "Additional Instruction",
        "Added Date",
        "Acknowledgement Date",
    ]
    lines: List[str] = [f"- {k}: {str(row.get(k, '') or '')}" for k in keys]
    return "\n".join(lines)


def epic_description_adf(row: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap markdown description in a minimal ADF structure for compatibility."""
    text = epic_description_markdown(row)
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": text}
                ]
            }
        ]
    }


def story_description_adf(row: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap markdown description in a minimal ADF structure for compatibility."""
    text = story_description_markdown(row)
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": text}
                ]
            }
        ]
    }


def rows_from_df(df: pd.DataFrame) -> List[ExcelRow]:
    """Convert a normalized DataFrame (ensure_columns applied) into ExcelRow list."""
    rows: List[ExcelRow] = []
    for _, r in df.iterrows():
        d = r.to_dict()
        er = ExcelRow(
            bp_id=str(d.get("BP ID", "")),
            wp_order_id=str(d.get("WP Order ID", "")),
            wp_id=str(d.get("WP ID", "")),
            wp_name=str(d.get("WP Name", "")),
            wp_quantity=d.get("WP Quantity", 0),
            employee_name=str(d.get("Employee Name", "")),
            wp_order_status=str(d.get("WP Order Status", "")),
            requested_date=d.get("WP Requested Delivery Date", ""),
            readiness_date=d.get("WP Readiness Date", ""),
            approved_date=d.get("Approved Date", ""),
            submitted_date=d.get("Submitted Date", ""),
            cancelled_date=d.get("Cancelled Date", ""),
            po_start=d.get("PO StartDate", ""),
            po_end=d.get("PO EndDate", ""),
            acknowledged_date=d.get("Acknowledgement Date", ""),
            added_date=d.get("Added Date", ""),
            updated_date=d.get("Updated Date", ""),
            std=d.get("STD", 0),
            market=str(d.get("Market", "")),
            sow_pa=str(d.get("SOW/PA", "")),
            po_number=str(d.get("PO Number", "")),
            wp_completed_qty=d.get("WP Completed Qty", 0),
            wp_final_quantity=d.get("WP Final Quantity", 0),
            total_approved_quantity=d.get("Total Approved Quantity", 0),
            in_time_delivery=str(d.get("In-Time Delivery", "")),
            customer_region_pm=str(d.get("Customer Region PM", "")),
            additional_instruction=str(d.get("Additional Instruction", "")),
            approved_rejected_reason=str(d.get("Approved/Rejected Reason", "")),
            survey_satisfaction_mark=str(d.get("Survey Satisfaction Mark", "")),
            survey_first_right=str(d.get("Survey First Right", "")),
            survey_suggestion=str(d.get("Survey Suggestion", "")),
            order_id=str(d.get("WP Order ID", "")),
            order_status=str(d.get("WP Order Status", "")),
            project_name=str(d.get("Project Name", "")),
            product=str(d.get("Product", "")),
            domain1=str(d.get("Domain", "") or d.get("Domain1", "")),
            customer=str(d.get("Customer", "")),
        )
        rows.append(er)
    return rows


def groups_from_rows(rows: List[ExcelRow]) -> List[WprGroup]:
    """Group ExcelRow list by BP ID into WprGroup with metadata from the first row per group."""
    by_bp: Dict[str, List[ExcelRow]] = {}
    for er in rows:
        by_bp.setdefault(er.bp_id or "", []).append(er)
    groups: List[WprGroup] = []
    for bp, lst in by_bp.items():
        head = lst[0]
        groups.append(
            WprGroup(
                bp_id=bp,
                project_name=head.project_name,
                product=head.product,
                domain1=head.domain1,
                customer=head.customer,
                rows=lst,
            )
        )
    return groups


def group_by_domain_then_bp(df: pd.DataFrame) -> List[tuple[str, List[tuple[str, pd.DataFrame]]]]:
    """Return list of (domain, [(bp_id, subdf), ...]). Domain is taken from canonical Domain column
    (fallback to Domain1 when Domain is empty)."""
    # Ensure canonicalization used earlier
    work = df.copy()
    if "Domain" not in work.columns and "Domain1" in work.columns:
        work["Domain"] = work["Domain1"]
    if "Domain" in work.columns and "Domain1" in work.columns:
        dom = work["Domain"].fillna("").astype(str).str.strip()
        dom1 = work["Domain1"].fillna("").astype(str).str.strip()
        work.loc[dom.eq("") & dom1.ne(""), "Domain"] = work.loc[dom.eq("") & dom1.ne(""), "Domain1"]

    result: List[tuple[str, List[tuple[str, pd.DataFrame]]]] = []
    for dom_val, dom_df in work.groupby("Domain", dropna=False):
        bp_groups = [(bp, sub) for bp, sub in dom_df.groupby("BP ID", dropna=False)]
        result.append((str(dom_val or ""), bp_groups))
    return result
