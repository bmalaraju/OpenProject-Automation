"""
Test script to create a single work package and see the actual error
"""
import sys
import os
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

from wpr_agent.services.provider import make_service
from wpr_agent.models import TrackerFieldMap

# Initialize service
svc = make_service()

# Get field map for FlowOne
try:
    fieldmap = svc.discover_fieldmap("FlowOne")
    print(f"Field map discovered:")
    print(f"  Custom fields: {list(fieldmap.discovered_custom_fields.keys())}")
except Exception as e:
    print(f"Error discovering fieldmap: {e}")
    fieldmap = TrackerFieldMap()

# Try to create a simple Epic
epic_fields = svc.build_epic_fields(
    project_key="FlowOne",
    summary="Test Epic :: WPO00000001",
    description_adf={"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Test description"}]}]}
)

print(f"\nEpic fields to be sent:")
for key, value in epic_fields.items():
    print(f"  {key}: {value}")

# Attempt creation
ok, result, retries, dropped = svc.create_issue_resilient(epic_fields, max_retries=1, backoff_base=0.5)

print(f"\nCreation result:")
print(f"  OK: {ok}")
print(f"  Result: {result}")
