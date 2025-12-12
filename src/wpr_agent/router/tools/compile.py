from __future__ import annotations

"""
Compile tools for Step 11 Router (Phase 2).

Tools
- compile_bundle_tool(domain, project_key, fieldmap, bp_groups) -> PlanBundle
  Compile a deterministic PlanBundle for the given domain/project from WprGroups.
"""

from typing import List

from wpr_agent.models import TrackerFieldMap, PlanBundle, WprGroup
from wpr_agent.planner.compile import compile_bundle
from wpr_agent.router.utils import log_kv


def compile_bundle_tool(
    domain: str,
    project_key: str,
    fieldmap: TrackerFieldMap,
    bp_groups: List[WprGroup],
) -> PlanBundle:
    """Compile PlanBundle for a domain/project.

    Inputs
    - domain: raw domain label (e.g., 'Cloud Infra')
    - project_key: Jira project key
    - fieldmap: JiraFieldMap (can be empty if offline)
    - bp_groups: list of WprGroup derived from Excel rows

    Returns
    - PlanBundle with epic/story plans and warnings

    Side effects
    - Logs counts for epics/stories and number of warnings
    """
    bundle = compile_bundle(domain, project_key, fieldmap, bp_groups)
    epics = len(bundle.product_plans)
    stories = sum(len(bp.stories) for bp in bundle.product_plans)
    warns = sum(len(bp.warnings) for bp in bundle.product_plans) + len(bundle.warnings)
    log_kv("compile_bundle", domain=domain, project=project_key, epics=epics, stories=stories, warnings=warns)
    return bundle

