from __future__ import annotations

from typing import Dict, List, Tuple

from wpr_agent.models import (
    AnnotatedIssuePlan,
    ProductPlan,
    ProductValidation,
    PlanBundle,
    StoryValidation,
    ValidationReport,
    ValidationSummary,
    ValidationSummary,
    TrackerFieldMap,
)


ALLOWED_WP_STATUSES: List[str] = [
    "Acknowledge",
    "Approved",
    "Cancelled",
    "Objected",
    "Pending Acknowledgement",
    "Pending Approval",
    "Rejected",
    "Waiting for order submission",
]


def _epic_natural_key(project_key: str, bp_id: str) -> str:
    return f"EPIC::{project_key}::{bp_id}"


def _extract_story_identity(st: AnnotatedIssuePlan) -> str:
    # Prefer identity annotation
    if st.identity and st.identity.get("value"):
        return str(st.identity["value"]).strip()
    # Fallback heuristic: first segment of summary
    parts = [p.strip() for p in (st.plan.summary or "").split("|")]
    return parts[0] if parts and parts[0] else ""


def _summary_too_long(summary: str, limit: int = 255) -> bool:
    return len(summary or "") > limit


def validate_bp_plan(bp_plan: ProductPlan, fieldmap: TrackerFieldMap) -> ProductValidation:
    v = ProductValidation(bp_id=bp_plan.bp_id)
    epic_ref = bp_plan.epic.natural_key or _epic_natural_key(bp_plan.epic.plan.project_key, bp_plan.bp_id)
    expected_ref = _epic_natural_key(bp_plan.epic.plan.project_key, bp_plan.bp_id)

    # Epic natural key sanity
    if epic_ref != expected_ref:
        v.errors.append(f"Epic natural_key mismatch: got '{epic_ref}', expected '{expected_ref}'")
        v.epic_ok = False

    # Required Epic Name when discovered
    if fieldmap and fieldmap.epic_name_field_id:
        if fieldmap.epic_name_field_id not in (bp_plan.epic.plan.fields or {}):
            v.errors.append("Epic missing required 'Epic Name' field")
            v.epic_ok = False

    # Epic summary length
    if _summary_too_long(bp_plan.epic.plan.summary):
        v.errors.append("Epic summary exceeds 255 chars")
        v.epic_ok = False

    # Story validations
    story_ids: Dict[str, int] = {}
    for st in bp_plan.stories:
        sv = StoryValidation(natural_key=st.natural_key)
        # Link intent
        intent = (st.link_intent or {}).get("epic_ref")
        if intent != expected_ref:
            sv.errors.append(f"Story epic_ref '{intent}' must match '{expected_ref}'")
        # Identity presence
        sid = _extract_story_identity(st)
        if not sid:
            sv.errors.append("Missing Story identity (WP Order ID)")
        else:
            story_ids[sid.upper()] = story_ids.get(sid.upper(), 0) + 1
        # Required fields (basic mapping)
        reqs = (fieldmap.required_fields_by_type or {}).get("story", []) if fieldmap else []
        # 'Due date' required maps to 'duedate'
        if any(r.strip().lower() == "due date" for r in reqs):
            if "duedate" not in (st.plan.fields or {}):
                sv.errors.append("Story missing required 'Due date'")
        # Start Date enforcement: if Acknowledgement present, Start date (standard or WPR) must equal it
        try:
            low = {k.strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
            # Get acknowledgement value from fields if available, else try description text
            ack_fids = [low.get("wpr acknowledgement date"), low.get("wpr acknowledgment date")]
            ack_val = None
            for fid in ack_fids:
                if fid and (st.plan.fields or {}).get(fid):
                    ack_val = str((st.plan.fields or {}).get(fid))
                    break
            if not ack_val:
                # parse description (markdown) for '- Acknowledgement Date: <value>'
                desc = st.plan.description or ""
                try:
                    for line in desc.splitlines():
                        if line.strip().lower().startswith("- acknowledgement date:"):
                            ack_val = line.split(":", 1)[1].strip()
                            break
                except Exception:
                    pass
            if ack_val:
                # Normalize to date-only (YYYY-MM-DD)
                ack_norm = ack_val.split("T", 1)[0]
                start_supported = getattr(fieldmap, "start_date_supported", False)
                if start_supported:
                    fid = low.get("start date")
                    if fid:
                        st_val = (st.plan.fields or {}).get(fid)
                        if st_val is None or str(st_val).strip() == "":
                            sv.warnings.append("Start date supported but not set from Acknowledgement Date")
                        else:
                            st_norm = str(st_val).split("T", 1)[0]
                            if st_norm != ack_norm:
                                sv.errors.append("Start date must equal Acknowledgement Date when present")
                    else:
                        sv.warnings.append("Start date supported but field id not discovered on screens")
                else:
                    fid = low.get("wpr start date")
                    if fid:
                        st_val = (st.plan.fields or {}).get(fid)
                        if st_val is None or str(st_val).strip() == "":
                            sv.warnings.append("WPR Start Date not set from Acknowledgement Date")
                        else:
                            st_norm = str(st_val).split("T", 1)[0]
                            if st_norm != ack_norm:
                                sv.errors.append("WPR Start Date must equal Acknowledgement Date when present")
                    else:
                        sv.warnings.append("WPR Start Date field not discovered on screens")
        except Exception:
            pass
        # Summary length
        if _summary_too_long(st.plan.summary):
            sv.errors.append("Story summary exceeds 255 chars")
        sv.ok = not sv.errors
        if not sv.ok:
            v.stories_ok = False
        v.story_results.append(sv)

    # Duplicate identities within product
    dups = [k for k, c in story_ids.items() if c > 1]
    if dups:
        v.errors.append(f"Duplicate Story identity within product {bp_plan.bp_id}: {', '.join(dups)}")
        v.stories_ok = False

    # Some model versions may not define `ok` on BPValidation; set when available.
    try:
        v.ok = not v.errors  # type: ignore[attr-defined]
    except Exception:
        pass
    return v


def validate_bundle(bundle: PlanBundle, fieldmap: TrackerFieldMap) -> ValidationReport:
    rep = ValidationReport(domain=bundle.domain, project_key=bundle.project_key)
    # Validate each product plan (legacy: BP)
    for bp in bundle.product_plans:
        bpr = validate_bp_plan(bp, fieldmap)
        rep.product_results.append(bpr)

    # Cross-order duplicate Story identities (same project; legacy: BP)
    id_to_refs: Dict[str, List[Tuple[str, str]]] = {}
    for bpr in rep.product_results:
        for sv in bpr.story_results:
            # Derive identity back from natural_key or by parsing st; best effort
            # Assume natural_key format STORY::<project>::<id or summary>
            try:
                parts = sv.natural_key.split("::", 2)
                ident = parts[2]
            except Exception:
                ident = sv.natural_key
            key = ident.upper()
            if key:
                id_to_refs.setdefault(key, []).append((bpr.bp_id, sv.natural_key))
    for ident, refs in id_to_refs.items():
        if len(refs) > 1:
            # Only treat as an error when the duplicate identity spans multiple distinct orders (bp_ids)
            distinct_orders = sorted({r[0] for r in refs})
            if len(distinct_orders) > 1:
                rep.errors.append(
                    f"Duplicate Story identity across orders in project {bundle.project_key}: {ident} -> {distinct_orders}"
                )
                # Also annotate individual story results with an error
                for bpr in rep.product_results:
                    for sv in bpr.story_results:
                        if ident in sv.natural_key.upper():
                            sv.errors.append("Duplicate identity across different orders in same project")
                            sv.ok = False
                            bpr.stories_ok = False
            else:
                # Duplicate identity only within a single order id (likely artifact); reduce severity to a warning
                rep.warnings.append(
                    f"Duplicate Story identity within order {distinct_orders[0]} in project {bundle.project_key}: {ident}"
                )

    # Determine overall ok
    rep.ok = not rep.errors and all((bpr.epic_ok and bpr.stories_ok and not bpr.errors) for bpr in rep.product_results)
    return rep


def validate_bundles(bundles: List[PlanBundle], fieldmaps: Dict[str, TrackerFieldMap]) -> ValidationSummary:
    out = ValidationSummary()
    for b in bundles:
        fmap = fieldmaps.get(b.project_key, TrackerFieldMap())
        out.reports.append(validate_bundle(b, fmap))
    totals = {"errors": 0, "warnings": 0, "orders": 0}
    for r in out.reports:
        totals["orders"] += len(getattr(r, "product_results", []) or [])
        totals["errors"] += len(r.errors) + sum(len(b.errors) for b in (r.product_results or []))
        totals["warnings"] += len(r.warnings) + sum(len(b.warnings) for b in (r.product_results or []))
    out.totals = totals
    return out
