from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel, Field, validator


def _to_iso(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if s == "":
        return ""
    ts = pd.to_datetime(s, errors="coerce", utc=False)
    if pd.isna(ts):
        return ""
    # Prefer date-only when no time component
    try:
        if int(ts.hour) or int(ts.minute) or int(ts.second):
            return ts.isoformat()
    except Exception:
        pass
    return ts.date().isoformat()


def _to_int(value: Any) -> int:
    try:
        s = str(value).replace(",", "").strip()
        if not s:
            return 0
        return int(float(s))
    except Exception:
        return 0


class ExcelRow(BaseModel):
    # Identity
    bp_id: str = Field("")
    wp_order_id: str = Field("")
    wp_id: str = Field("")
    wp_name: str = Field("")
    wp_quantity: int = Field(0)
    employee_name: str = Field("")

    # Status
    wp_order_status: str = Field("")

    requested_date: str = Field("")
    readiness_date: str = Field("")
    approved_date: str = Field("")
    submitted_date: str = Field("")
    cancelled_date: str = Field("")
    po_start: str = Field("")
    po_end: str = Field("")
    acknowledged_date: str = Field("")
    added_date: str = Field("")
    updated_date: str = Field("")
    objected_date: str = Field("")
    rejected_date: str = Field("")
    effective_updated_date: str = Field("")
    std: int = Field(0)

    # Extended optional fields for Epic/Story description schema
    market: str = Field("")
    sow_pa: str = Field("")
    po_number: str = Field("")
    wp_completed_qty: int = Field(0)
    wp_final_quantity: int = Field(0)
    total_approved_quantity: int = Field(0)
    in_time_delivery: str = Field("")
    customer_region_pm: str = Field("")
    additional_instruction: str = Field("")
    approved_rejected_reason: str = Field("")
    survey_satisfaction_mark: str = Field("")
    survey_first_right: str = Field("")
    survey_suggestion: str = Field("")

    order_id: str = Field("")
    order_status: str = Field("")

    project_name: str = Field("")
    product: str = Field("")
    domain1: str = Field("")
    customer: str = Field("")

    target_due_date: str = Field("")

    @validator("wp_quantity", pre=True)
    def v_qty(cls, v):
        return _to_int(v)

    @validator("std", pre=True)
    def v_std(cls, v):
        return _to_int(v)

    @validator("wp_completed_qty", pre=True)
    def v_completed_qty(cls, v):
        return _to_int(v)

    @validator("wp_final_quantity", pre=True)
    def v_final_qty(cls, v):
        return _to_int(v)

    @validator("total_approved_quantity", pre=True)
    def v_total_approved_qty(cls, v):
        return _to_int(v)

    @validator(
        "requested_date",
        "readiness_date",
        "approved_date",
        "submitted_date",
        "cancelled_date",
        "po_start",
        "po_end",
        "acknowledged_date",
        "added_date",
        "updated_date",
        pre=True,
    )
    def v_dates(cls, v):
        return _to_iso(v)

    @validator("target_due_date", always=True)
    def v_due(cls, v, values):
        # Requested → Readiness → Approved
        for k in ("requested_date", "readiness_date", "approved_date"):
            d = values.get(k, "")
            if isinstance(d, str) and d.strip():
                return d
        return ""

    @validator("wp_order_status", pre=True)
    def v_status_normalize(cls, v):
        s = (str(v or "").strip()).lower()
        mapping = {
            "acknowledge": "Acknowledge",
            "acknowledged": "Acknowledge",
            "approved": "Approved",
            "cancelled": "Cancelled",
            "canceled": "Cancelled",
            "objected": "Objected",
            "pending acknowledgement": "Pending Acknowledgement",
            "pending acknowledgment": "Pending Acknowledgement",
            "pending approval": "Pending Approval",
            "rejected": "Rejected",
            "waiting for order submission": "Waiting for order submission",
        }
        return mapping.get(s, v)

    @validator("effective_updated_date", always=True)
    def v_effective_update(cls, v, values):
        status = values.get("wp_order_status", "") or ""
        added = values.get("added_date", "") or ""
        ack = values.get("acknowledged_date", "") or ""
        submitted = values.get("submitted_date", "") or ""
        approved = values.get("approved_date", "") or ""
        cancelled = values.get("cancelled_date", "") or ""
        # Derive objected/rejected date from submitted when applicable
        if (str(status).lower() == "objected"):
            values["objected_date"] = submitted or ""
            return submitted or ""
        if (str(status).lower() == "rejected"):
            values["rejected_date"] = submitted or ""
            return submitted or ""
        if status == "Pending Acknowledgement":
            return added or ""
        if status == "Acknowledge":
            return ack or ""
        if status == "Pending Approval":
            return submitted or ""
        if status == "Approved":
            return approved or ""
        if status == "Cancelled":
            return cancelled or ""
        if status == "Waiting for order submission":
            return ack or added or ""
        # Default: keep original updated_date if provided
        upd = values.get("updated_date", "") or ""
        return upd


class WprGroup(BaseModel):
    bp_id: str
    project_name: str

    # Validators removed as they referenced fields not present in WprGroup


class WprGroup(BaseModel):
    bp_id: str
    project_name: str
    product: str
    domain1: str
    customer: str
    rows: List[ExcelRow]


class TrackerFieldMap(BaseModel):
    # Generic field map container
    required_fields_by_type: Dict[str, List[str]] = Field(default_factory=dict)
    discovered_custom_fields: Dict[str, str] = Field(default_factory=dict)
    epic_name_field_id: Optional[str] = None
    epic_link_field_id: Optional[str] = None
    start_date_supported: bool = False


class IssuePlan(BaseModel):
    issue_type: str
    project_key: str
    summary: str
    description: str = Field("")
    description_adf: Optional[Dict[str, Any]] = None
    fields: Dict[str, Any] = Field(default_factory=dict)
    parent_key: Optional[str] = None


class RunReport(BaseModel):
    created_epics: List[str] = Field(default_factory=list)
    created_stories: List[str] = Field(default_factory=list)
    created_subtasks: List[str] = Field(default_factory=list)
    updated_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    failures: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)


class AnnotatedIssuePlan(BaseModel):
    plan: IssuePlan
    natural_key: str
    identity: Optional[Dict[str, str]] = None
    link_intent: Optional[Dict[str, str]] = None


class ProductPlan(BaseModel):
    # Retain original grouping identifier naming semantics as a data key
    # (historically mapped from Excel "BP ID" or order id in product route).
    bp_id: str
    epic: AnnotatedIssuePlan
    stories: List[AnnotatedIssuePlan] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class PlanBundle(BaseModel):
    domain: str
    project_key: str
    product_plans: List[ProductPlan] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class StoryValidation(BaseModel):
    natural_key: str
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    ok: bool = True


class ProductValidation(BaseModel):
    bp_id: str
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    epic_ok: bool = True
    stories_ok: bool = True
    story_results: List[StoryValidation] = Field(default_factory=list)


class ValidationReport(BaseModel):
    domain: str
    project_key: str
    product_results: List[ProductValidation] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    ok: bool = True


class ValidationSummary(BaseModel):
    reports: List[ValidationReport] = Field(default_factory=list)
    totals: Dict[str, int] = Field(default_factory=dict)
