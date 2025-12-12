from __future__ import annotations

"""
Validation tools for Step 11 Router (Phase 2).

Tools
- validate_bundle_tool(bundle, fieldmap) -> ValidationReport
  Validate a PlanBundle against chain constraints and required fields.

- decide_apply_tool(report, continue_on_error) -> (allowed_ids, blocked_ids)
  Derive which order IDs (legacy: BP IDs) are eligible for apply based on validation and policy.
"""

from wpr_agent.models import TrackerFieldMap, PlanBundle, ValidationReport, ProductValidation, StoryValidation

# Import log_kv utility (with fallback)
try:
    from wpr_agent.router.utils import log_kv
except ImportError:
    def log_kv(event: str, **kv):
        """Fallback log_kv if router utils not available."""
        print(f"{event}: {kv}")

# Local implementation of validator (replacing missing wpr_agent.validator.plan_validate)
def validate_bundle(bundle: PlanBundle, fieldmap: TrackerFieldMap) -> ValidationReport:
    """
    Basic validation of PlanBundle.
    """
    product_results = []
    
    for plan in bundle.product_plans:
        # Validate Epic
        epic_ok = True
        epic_errors = []
        if not plan.epic:
            epic_ok = False
            epic_errors.append("Missing Epic plan")
            
        # Validate Stories
        story_results = []
        stories_ok = True
        for story in plan.stories:
            story_ok = True
            story_errors = []
            if not story.plan.summary:
                story_ok = False
                story_errors.append("Missing story summary")
                
            story_results.append(StoryValidation(
                natural_key=story.natural_key,
                ok=story_ok,
                errors=story_errors,
                warnings=[]
            ))
            if not story_ok:
                stories_ok = False
                
        product_results.append(ProductValidation(
            bp_id=plan.bp_id,
            epic_ok=epic_ok,
            stories_ok=stories_ok,
            errors=epic_errors,
            warnings=[],
            story_results=story_results
        ))
        
    return ValidationReport(
        domain=bundle.domain,
        project_key=bundle.project_key,
        ok=all(pr.epic_ok and pr.stories_ok for pr in product_results),
        errors=[],
        warnings=[],
        product_results=product_results
    )

import os


def validate_bundle_tool(bundle: PlanBundle, fieldmap: TrackerFieldMap) -> ValidationReport:
    """Validate a PlanBundle; offline mode yields limited checks.

    Inputs
    - bundle: PlanBundle produced by compile
    - fieldmap: JiraFieldMap (empty map means limited checks)

    Returns
    - ValidationReport with per-BP results, errors, and warnings

    Side effects
    - Logs ok/errors/warnings counts
    """
    rep = validate_bundle(bundle, fieldmap)
    # Provider-aware required field precheck for OpenProject to avoid server-side 400s
    # Provider-aware required field precheck for OpenProject to avoid server-side 400s
    try:
        # Provider-aware required field precheck for OpenProject
        low = {str(k).strip().lower(): v for k, v in (fieldmap.discovered_custom_fields or {}).items()}
        # Required sets (display names)
        # Required sets (display names)
        epic_required = [
            "wpr project",
            "wpr product",
            "wpr domain",
            "wpr po start date",
            "wpr po end date",
            "wpr wp id",
            "wpr wp name",
            "wpr wp order id",
            "wpr wp order status",
            "wpr wp quantity",
        ]
        # Story required set (User story): make Status optional; keep ID/Name/Order ID
        story_required = [
            "wpr wp id",
            "wpr wp name",
            "wpr wp order id",
        ]
        # Build id sets
        epic_req_ids = [low.get(n) for n in epic_required if low.get(n)]
        story_req_ids = [low.get(n) for n in story_required if low.get(n)]
        # Build lookup from bundle for fields by bp_id and natural_key
        bp_lookup = {pp.bp_id: pp for pp in (bundle.product_plans or [])}
        for bpr in rep.product_results:
            pp = bp_lookup.get(bpr.bp_id)
            # Epic precheck
            try:
                ep_fields = (pp.epic.plan.fields if pp and pp.epic and pp.epic.plan else {}) or {}
            except Exception:
                ep_fields = {}
            missing_ep = [n for n in epic_required if (low.get(n) and (str(ep_fields.get(low.get(n), "")).strip() == ""))]
            if missing_ep:
                bpr.errors.append("Epic missing required fields (OpenProject): " + ", ".join(sorted(set(missing_ep))))
                bpr.epic_ok = False
                try:
                    from wpr_agent.router.utils import log_kv as _log
                    _log("epic_required_missing", project=bundle.project_key, bp_id=bpr.bp_id, missing=sorted(set(missing_ep)))
                except Exception:
                    pass
            # Story precheck
            new_story_results = []
            for sv in bpr.story_results:
                # Find the story plan by natural_key
                st_fields = {}
                try:
                    if pp:
                        for ann in (pp.stories or []):
                            if getattr(ann, 'natural_key', None) == sv.natural_key:
                                st_fields = (ann.plan.fields or {})
                                break
                except Exception:
                    st_fields = {}
                # Check custom fields
                missing_st = [n for n in story_required if (low.get(n) and (str(st_fields.get(low.get(n), "")).strip() == ""))]
                # Due date (standard) is optional for User stories
                # If desired, we could append a warning instead of an error when missing.
                # if str(st_fields.get('duedate','')).strip() == "":
                #     sv.warnings.append("Story 'Due date' not set (optional)")
                if missing_st:
                    sv.errors.append("Story missing required fields (OpenProject): " + ", ".join(sorted(set(missing_st))))
                    sv.ok = False
                    bpr.stories_ok = False
                    try:
                        from wpr_agent.router.utils import log_kv as _log
                        _log("story_required_missing", project=bundle.project_key, bp_id=bpr.bp_id, story=sv.natural_key, missing=sorted(set(missing_st)))
                    except Exception:
                        pass
                new_story_results.append(sv)
            bpr.story_results = new_story_results
    except Exception:
        # Do not block on validator errors
        pass
    order_errors = sum(len(b.errors) for b in rep.product_results)
    warns = sum(len(b.warnings) for b in rep.product_results) + len(rep.warnings)
    log_kv("validate_bundle", project=bundle.project_key, ok=rep.ok, order_errors=order_errors, warnings=warns)
    return rep


def decide_apply_tool(report: ValidationReport, continue_on_error: bool) -> Tuple[Set[str], Set[str]]:
    """Produce allowed and blocked order ID sets for apply (legacy: BP IDs).

    Inputs
    - report: ValidationReport
    - continue_on_error: if False, block apply entirely when errors exist; if True, filter to passing orders (legacy: BPs)

    Returns
    - (allowed_ids, blocked_ids)

    Side effects
    - Logs allowed vs blocked sizes
    """
    # If strict and there are bundle-level errors, block all orders (legacy: BPs)
    bundle_has_errors = bool(report.errors)
    allowed: Set[str] = set()
    blocked: Set[str] = set()
    for bpr in report.product_results:
        has_order_errors = bool(bpr.errors)
        if not has_order_errors:
            allowed.add(bpr.bp_id)
        else:
            blocked.add(bpr.bp_id)

    if not continue_on_error and (bundle_has_errors or blocked):
        # Block everything when strict
        blocked = {bpr.bp_id for bpr in report.product_results}
        allowed = set()

    log_kv("decide_apply", allowed=len(allowed), blocked=len(blocked), continue_on_error=continue_on_error)
    return allowed, blocked

