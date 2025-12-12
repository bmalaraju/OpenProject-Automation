import pytest
from unittest.mock import patch, MagicMock
from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2

@pytest.fixture
def mock_op_client():
    with patch("wpr_agent.services.openproject_service_v2.OpenProjectClient") as mock:
        yield mock

def test_create_issue_resilient_success(mock_op_client):
    # Setup
    service = OpenProjectServiceV2()
    mock_client_instance = mock_op_client.return_value
    
    # Mock resolve_project
    mock_client_instance.resolve_project.return_value = {"id": "100"}
    # Mock list_types
    mock_client_instance.list_types_for_project.return_value = {"epic": {"id": "1"}}
    # Mock create response
    mock_client_instance.create_work_package.return_value = (201, {"id": "WP-500"})
    
    # Execute
    fields = {
        "project": {"key": "TEST"},
        "issuetype": {"name": "Epic"},
        "summary": "Test Epic"
    }
    ok, res, retries, dropped = service.create_issue_resilient(fields)
    
    # Verify
    assert ok is True
    assert res["key"] == "WP-500"
    assert retries == 0
    
    # Verify payload
    mock_client_instance.create_work_package.assert_called_once()
    payload = mock_client_instance.create_work_package.call_args[0][0]
    assert payload["subject"] == "Test Epic"
    assert payload["_links"]["project"]["href"] == "/api/v3/projects/100"
    assert payload["_links"]["type"]["href"] == "/api/v3/types/1"

def test_create_issue_resilient_retry(mock_op_client):
    # Setup
    service = OpenProjectServiceV2()
    mock_client_instance = mock_op_client.return_value
    mock_client_instance.resolve_project.return_value = {"id": "100"}
    mock_client_instance.list_types_for_project.return_value = {"epic": {"id": "1"}}
    
    # Mock create response: 429 then 201
    mock_client_instance.create_work_package.side_effect = [
        (429, {"Retry-After": "0.1"}),
        (201, {"id": "WP-501"})
    ]
    
    # Execute
    fields = {"project": {"key": "TEST"}, "issuetype": {"name": "Epic"}}
    ok, res, retries, dropped = service.create_issue_resilient(fields, max_retries=2)
    
    # Verify
    assert ok is True
    assert res["key"] == "WP-501"
    assert retries == 1
    assert mock_client_instance.create_work_package.call_count == 2
