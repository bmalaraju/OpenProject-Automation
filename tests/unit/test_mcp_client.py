import pytest
from unittest.mock import patch, MagicMock
from wpr_agent.mcp.client import apply_bp

@pytest.fixture
def mock_call_tool():
    with patch("wpr_agent.mcp.client.call_tool") as mock:
        yield mock

def test_apply_bp_adapter_flow(mock_call_tool):
    # Setup inputs
    project_key = "TEST"
    bp_plan = {
        "product_plans": [
            {
                "epic": {
                    "plan": {"summary": "Epic 1", "issue_type": "Epic", "fields": {}},
                    "identity": {"value": "BP-1"}
                },
                "stories": [
                    {
                        "plan": {"summary": "Story 1", "issue_type": "Story", "fields": {}},
                        "identity": {"value": "ORD-1"}
                    }
                ]
            }
        ]
    }
    
    # Setup mock responses
    # 1. Resolve Epic -> Not found
    # 2. Resolve Story -> Found (ID: 100)
    # 3. Apply -> Created Epic (ID: 200), Updated Story (ID: 100)
    # 4. Register Epic (ID: 200)
    
    def side_effect(tool, params):
        if tool == "wpr.resolve_identity":
            if params["issue_type"] == "Epic":
                return {"ok": True, "issue_key": None}
            if params["issue_type"] == "Story":
                return {"ok": True, "issue_key": "100"}
        if tool == "openproject.apply_openproject_plan":
            return {
                "ok": True,
                "created": [{"id": "200", "subject": "Epic 1"}],
                "updated": [{"id": "100", "status": 200}],
                "errors": []
            }
        if tool == "wpr.register_identity":
            return {"ok": True}
        return {"ok": False, "error": "unknown tool"}
        
    mock_call_tool.side_effect = side_effect
    
    # Execute
    res = apply_bp(
        bundle_domain="Dom",
        project_key=project_key,
        fieldmap={},
        bp_plan=bp_plan,
        max_retries=1,
        backoff_base=1.0,
        dry_run=False
    )
    
    # Verify
    assert res is not None
    created, updated, warns, errs, stats, timings = res
    
    assert len(created) == 1
    assert created[0]["id"] == "200"
    assert len(updated) == 1
    assert updated[0]["id"] == "100"
    
    # Verify call sequence
    # 1. Resolve Epic
    mock_call_tool.assert_any_call("wpr.resolve_identity", {
        "project_key": "TEST", "order_id": "BP-1", "issue_type": "Epic"
    })
    # 2. Resolve Story
    mock_call_tool.assert_any_call("wpr.resolve_identity", {
        "project_key": "TEST", "order_id": "ORD-1", "issue_type": "Story", "instance": 0
    })
    # 3. Apply (Epic has no ID, Story has ID=100)
    apply_call = [c for c in mock_call_tool.call_args_list if c[0][0] == "openproject.apply_openproject_plan"][0]
    items = apply_call[0][1]["items"]
    assert len(items) == 2
    assert "id" not in items[0] # Epic
    assert items[1]["id"] == "100" # Story
    
    # 4. Register Epic
    mock_call_tool.assert_any_call("wpr.register_identity", {
        "project_key": "TEST", "order_id": "BP-1", "issue_key": "200", "issue_type": "Epic", "instance": 0
    })
