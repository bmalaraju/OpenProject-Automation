import pytest
from unittest.mock import MagicMock
from wpr_agent.planner.compile import compile_product_plan
from wpr_agent.models import WprGroup, TrackerFieldMap, IssuePlan

@pytest.fixture
def sample_group():
    # Create a mock WprGroup with minimal necessary data
    row = MagicMock()
    row.wp_order_id = "ORD-123"
    row.wp_id = "WP-001"
    row.wp_name = "Test WP"
    row.wp_quantity = 10
    row.requested_date = "2023-01-01"
    row.bp_id = "BP-999"
    row.domain1 = "TestDomain"
    
    group = MagicMock(spec=WprGroup)
    group.bp_id = "BP-999"
    group.project_name = "Test Project"
    group.product = "Test Product"
    group.domain1 = "TestDomain"
    group.customer = "Test Customer"
    group.rows = [row]
    return group

def test_compile_product_plan_basic(sample_group):
    # Test basic compilation without fieldmap
    fieldmap = TrackerFieldMap()
    epic, stories, warnings = compile_product_plan(sample_group, "TEST", fieldmap)
    
    assert isinstance(epic, IssuePlan)
    assert epic.issue_type == "Epic"
    assert epic.summary == "Test Project :: BP-999"
    
    assert len(stories) == 1
    assert stories[0].issue_type == "Story"
    assert stories[0].summary == "ORD-123 | WP-001 | Test WP"

def test_compile_product_plan_with_identity(sample_group):
    # Test compilation with identity field discovery
    fieldmap = TrackerFieldMap(
        discovered_custom_fields={
            "WPR WP Order ID": "customField1",
            "WPR BP ID": "customField2"
        }
    )
    epic, stories, warnings = compile_product_plan(sample_group, "TEST", fieldmap)
    
    # Epic should have BP ID
    assert epic.fields.get("customField2") == "BP-999"
    
    # Story should have Order ID
    assert stories[0].fields.get("customField1") == "ORD-123"

def test_compile_product_plan_missing_identity(sample_group):
    # Test warning generation when identity parts are missing
    sample_group.rows[0].wp_order_id = None
    sample_group.rows[0].wp_id = None
    sample_group.rows[0].wp_name = None
    
    fieldmap = TrackerFieldMap()
    epic, stories, warnings = compile_product_plan(sample_group, "TEST", fieldmap)
    
    assert len(warnings) > 0
    assert "Row missing Story identity parts" in warnings[0]
    assert stories[0].summary == "Work Package"
