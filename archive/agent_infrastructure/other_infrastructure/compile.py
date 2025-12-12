from __future__ import annotations

from typing import Any, Dict, List, Tuple

from wpr_agent.models import TrackerFieldMap, IssuePlan, WprGroup, PlanBundle, ProductPlan, AnnotatedIssuePlan
from wpr_agent.tools.excel_tools import epic_summary, epic_description_markdown, story_description_markdown


def _meta_from_group(bp: WprGroup) -> Dict[str, Any]:
    return {
        "project_name": bp.project_name or "",
        "product": bp.product or "",
        "domain": bp.domain1 or "",
        "customer": bp.customer or "",
    }


def _choose_identity_field(discovered: Dict[str, str], candidates: List[str]) -> str | None:
    if not discovered:
        return None
    lowmap = {k.strip().lower(): v for k, v in discovered.items()}
    for name in candidates:
        v = lowmap.get(name.strip().lower())
        if v:
            return v
    return None


def compile_product_plan(bp: WprGroup, project_key: str, fieldmap: TrackerFieldMap) -> Tuple[IssuePlan, List[IssuePlan], List[str]]:
    warnings: List[str] = []
    # Epic plan
    summary = bp.bp_id # Use Order ID as Epic Summary
    # Build a row-like dict using the first row in the group to feed description schema
    head = bp.rows[0] if bp.rows else None
    row0: Dict[str, Any] = {
        "WP Order ID": head.wp_order_id if head else "",
        "WP Order Status": head.wp_order_status if head else "",
        "Domain": bp.domain1 or "",
        "Market": head.market if head else "",
        "SOW/PA": head.sow_pa if head else "",
        "PO Number": head.po_number if head else "",
        "PO StartDate": head.po_start if head else "",
        "PO EndDate": head.po_end if head else "",
        "Product": bp.product or "",
        "WP ID": head.wp_id if head else "",
        "WP Name": head.wp_name if head else "",
        "WP Quantity": head.wp_quantity if head else "",
        "WP Completed Qty": head.wp_completed_qty if head else "",
        "WP Final Quantity": head.wp_final_quantity if head else "",
        "Total Approved Quantity": head.total_approved_quantity if head else "",
        "WP Requested Delivery Date": head.requested_date if head else "",
        "WP Readiness Date": head.readiness_date if head else "",
        "In-Time Delivery": head.in_time_delivery if head else "",
        "Project Name": bp.project_name or "",
        "Customer": bp.customer or "",
        "Customer Region PM": head.customer_region_pm if head else "",
        "Additional Instruction": head.additional_instruction if head else "",
        "Approved/Rejected Reason": head.approved_rejected_reason if head else "",
        "Added Date": head.added_date if head else "",
        "Updated Date": head.updated_date if head else "",
        "Acknowledgement Date": head.acknowledged_date if head else "",
        "Cancelled Date": head.cancelled_date if head else "",
        "Submitted Date": head.submitted_date if head else "",
        "Approved Date": head.approved_date if head else "",
        "STD": head.std if head else 0,
        "Survey Satisfaction Mark": head.survey_satisfaction_mark if head else "",
        "Survey First Right": head.survey_first_right if head else "",
        "Survey Suggestion": head.survey_suggestion if head else "",
    }
    desc = epic_description_markdown(row0)
    epic_fields: Dict[str, Any] = {}
    # Legacy JIRA 'Epic Name' field logic removed

    # Try to set identity custom field for BP ID if discovered
    if fieldmap and fieldmap.discovered_custom_fields:
        dcf = {k.strip().lower(): v for k, v in fieldmap.discovered_custom_fields.items()}
        # Epic identity (optional)
        bp_id_field = _choose_identity_field(fieldmap.discovered_custom_fields, ["wpr bp id", "bp id"])
        if bp_id_field:
            epic_fields[bp_id_field] = bp.bp_id
        # Additional Epic meta fields when present
        def eput(name: str, value: Any) -> None:
            fid = dcf.get(name.strip().lower())
            if fid is not None and value not in (None, ""):
                epic_fields[fid] = value
        eput("wpr project", bp.project_name)
        eput("wpr product", bp.product)
        eput("wpr domain", bp.domain1)
        eput("wpr customer", bp.customer)
        
        # Map Order-level fields to Epic
        eput("wpr wp order id", bp.bp_id)
        if head:
            eput("wpr wp order status", head.wp_order_status)
            eput("wpr po start date", head.po_start)
            eput("wpr po end date", head.po_end)
            eput("wpr added date", head.added_date)
    epic_plan = IssuePlan(
        issue_type="Epic",
        project_key=project_key,
        summary=summary,
        description=desc,
        fields=epic_fields,
        parent_key=None,
    )

    # User Stories
    story_plans: List[IssuePlan] = []
    # Discover Story identity field if any
    story_id_field: str | None = None
    if fieldmap and fieldmap.discovered_custom_fields:
        story_id_field = _choose_identity_field(fieldmap.discovered_custom_fields, ["wpr wp order id", "wp order id"])  # type: ignore[assignment]

    seen_wp_ids: set[str] = set()
    
    # Sort rows to ensure deterministic ordering
    sorted_rows = sorted(bp.rows, key=lambda r: (r.wp_id or "", r.wp_name or ""))
    
    global_item_index = 1
    
    for er in sorted_rows:
        # Missing identity will be validated at Step 8; we record a warning here and still compile with summary fallback
        if not (er.wp_order_id or er.wp_id or er.wp_name):
            warnings.append(f"Row missing Story identity parts in product {bp.bp_id}; will rely on generic summary")

        qty = er.wp_quantity if er.wp_quantity > 0 else 1
        
        for _ in range(qty):
            # Build Story summary: WPO...-N
            if er.wp_order_id:
                st_summary = f"{er.wp_order_id}-{global_item_index}"
            else:
                # Fallback if no order ID
                st_summary = f"{er.wp_name or 'Item'}-{global_item_index}"
            
            global_item_index += 1

            # Prepare a row-like dict for description ADF
            row_dict: Dict[str, Any] = {
                "WP Order ID": er.wp_order_id,
                "Product": er.product,
                "WP ID": er.wp_id,
                "WP Name": er.wp_name,
                "WP Requested Delivery Date": er.requested_date,
                "Additional Instruction": "",
                "Added Date": er.added_date,
                "Acknowledgement Date": er.acknowledged_date,
            }
            st_desc = story_description_markdown(row_dict)

            st_fields: Dict[str, Any] = {}
            if er.target_due_date:
                st_fields["duedate"] = er.target_due_date
            if story_id_field and er.wp_order_id:
                st_fields[story_id_field] = er.wp_order_id
            # Populate additional WPR fields when discovered
            if fieldmap and fieldmap.discovered_custom_fields:
                dcf = {k.strip().lower(): v for k, v in fieldmap.discovered_custom_fields.items()}
                def put(name: str, value: Any) -> None:
                    fid = dcf.get(name.strip().lower())
                    if fid is not None and value not in (None, ""):
                        st_fields[fid] = value
                put("wpr wp id", er.wp_id)
                put("wpr wp name", er.wp_name)
                put("wpr wp quantity", er.wp_quantity)
                # Skip setting select options unless configured; leave out to avoid 400s when options missing
                # put("wpr wp order status", er.wp_order_status)
                put("wpr requested date", er.requested_date)
                put("wpr readiness date", er.readiness_date)
                put("wpr approved date", er.approved_date)
                put("wpr submitted date", er.submitted_date)
                put("wpr cancelled date", er.cancelled_date)
                # Acknowledgement vs Acknowledgment spelling variants
                put("wpr acknowledgement date", er.acknowledged_date)
                put("wpr acknowledgment date", er.acknowledged_date)
                # Start Date mapping: prefer standard Start date when supported; otherwise WPR Start Date
                if getattr(fieldmap, "start_date_supported", False):
                    put("start date", er.acknowledged_date)
                else:
                    put("wpr start date", er.acknowledged_date)
                # Additional Story meta
                put("wpr bp id", er.bp_id)
                put("wpr domain", er.domain1)
                put("wpr employee name", er.employee_name)
                put("wpr po start date", er.po_start)
                put("wpr po end date", er.po_end)
                put("wpr added date", er.added_date)
                put("wpr updated date", er.updated_date)
                put("wpr std", er.std)

            story_plans.append(
                IssuePlan(
                    issue_type="User Story",
                    project_key=project_key,
                    summary=st_summary,
                    description=st_desc,
                    fields=st_fields,
                    parent_key=None,
                )
            )

        # Duplicate identity hint
        if er.wp_order_id:
            key = (er.wp_order_id or "").strip().upper()
            # Since we are suffixing, duplicates in same group are expected if multiple rows share order ID?
            # Actually, WprGroup is per BP ID (which seems to be Order ID in this context).
            # If multiple rows have same Order ID, they are items.
            pass

    return epic_plan, story_plans, warnings


def compile_domain_plans(
    domain: str,
    project_key: str,
    fieldmap: JiraFieldMap,
    bp_groups: List[WprGroup],
) -> Tuple[List[IssuePlan], List[str]]:
    plans: List[IssuePlan] = []
    warnings: List[str] = []
    for bp in bp_groups:
        ep, stories, warns = compile_product_plan(bp, project_key, fieldmap)
        plans.append(ep)
        plans.extend(stories)
        warnings.extend(warns)
    return plans, warnings


def compile_bundle(
    domain: str,
    project_key: str,
    fieldmap: TrackerFieldMap,
    bp_groups: List[WprGroup],
) -> PlanBundle:
    bundle = PlanBundle(domain=domain, project_key=project_key)
    for bp in bp_groups:
        ep, stories, warns = compile_product_plan(bp, project_key, fieldmap)
        ep_ann = AnnotatedIssuePlan(
            plan=ep,
            natural_key=f"EPIC::{project_key}::{bp.bp_id}",
            identity=None,
        )
        # Attach identity hint if available
        if fieldmap and fieldmap.discovered_custom_fields:
            fid = _choose_identity_field(fieldmap.discovered_custom_fields, ["wpr bp id", "bp id"]) or ""
            if fid:
                ep_ann.identity = {"field_id": fid, "value": bp.bp_id}
        st_anns: List[AnnotatedIssuePlan] = []
        for sp in stories:
            # Derive wp_order_id from plan fields if present
            wp_order_value = ""
            fid = _choose_identity_field(fieldmap.discovered_custom_fields or {}, ["wpr wp order id", "wp order id"]) if fieldmap else None
            if fid and sp.fields.get(fid):
                wp_order_value = str(sp.fields.get(fid))
            nat = f"STORY::{project_key}::{wp_order_value or sp.summary}"
            ident = {"field_id": fid, "value": wp_order_value} if fid and wp_order_value else None
            st_anns.append(
                AnnotatedIssuePlan(
                    plan=sp,
                    natural_key=nat,
                    identity=ident,
                    link_intent={"epic_ref": f"EPIC::{project_key}::{bp.bp_id}"},
                )
            )
        bundle.product_plans.append(ProductPlan(bp_id=bp.bp_id, epic=ep_ann, stories=st_anns, warnings=warns))
    return bundle
