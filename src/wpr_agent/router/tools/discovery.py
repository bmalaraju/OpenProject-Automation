"""
Discovery tools for Step 11 Router (Phase 2).

Tools
- discover_fieldmap_tool(project_key) -> TrackerFieldMap
  Discover Epic Link, Epic Name, Start Date, and required fields via createmeta (online only).
"""

import os
from wpr_agent.router.utils import log_kv
from wpr_agent.models import TrackerFieldMap

def discover_fieldmap_tool(project_key: str) -> TrackerFieldMap:
    """Discover key field information for a project.

    Inputs
    - project_key: Jira project key (e.g., 'CLDINF')

    Returns
    - JiraFieldMap with Epic Link field id, Epic Name field id, Start Date support, required fields, and discovered custom fields

    Side effects
    - Performs network calls to Jira (createmeta); prints discovered values
    """
    # MCP support removed - using direct service call only
    
    use_stub = os.getenv("ROUTER_JIRA_STUB") == "1"
    if use_stub:
        from wpr_agent.services.jira_service_stub import JiraServiceStub  # type: ignore
        svc = JiraServiceStub()
    else:
        # Provider-aware service factory
        from wpr_agent.services.provider import make_service  # type: ignore
        svc = make_service()
    
    try:
        fmap = svc.discover_fieldmap(project_key)
        log_kv(
            "discover_fieldmap",
            project=project_key,
            epic_link=fmap.epic_link_field_id,
            epic_name=fmap.epic_name_field_id,
            start_date=fmap.start_date_supported,
        )
        return fmap
    except Exception as ex2:
        print(f"[Discovery] Service error: {ex2}")
        return TrackerFieldMap()
