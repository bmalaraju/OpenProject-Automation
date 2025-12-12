
import os
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock

# Bootstrap env and paths
BASE_DIR = Path(__file__).resolve().parents[0]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2

def test_status_mapping():
    # Mock environment variables for overrides
    overrides_path = os.path.join(BASE_DIR, "config", "op_custom_option_overrides.json")
    field_id_path = os.path.join(BASE_DIR, "config", "op_field_id_overrides.json")
    os.environ["OP_CUSTOM_OPTION_OVERRIDES_PATH"] = overrides_path
    os.environ["OP_FIELD_ID_OVERRIDES_PATH"] = field_id_path
    
    print(f"Overrides path: {overrides_path}")
    print(f"Field ID path: {field_id_path}")

    svc = OpenProjectServiceV2()
    
    # Mock client methods to avoid network calls
    svc.client.list_custom_fields = MagicMock(return_value={}) # Force fallback to file
    svc.client.list_custom_options = MagicMock(return_value=[])
    svc.client.work_package_form = MagicMock(return_value=(404, {})) # Simulate no schema
    
    # Mock project resolution
    svc._project_cache["TEST"] = {"id": "123"}
    svc._types_cache["123"] = {"epic": {"id": "456"}}
    
    # Load field map to get the ID for "WPR WP Order Status"
    cf_map = svc._cf_map()
    print(f"Loaded CF Map keys: {list(cf_map.keys())}")
    status_fid = cf_map.get("wpr wp order status")
    print(f"Status Field ID: {status_fid}")
    
    if not status_fid:
        print("CRITICAL: Could not resolve status field ID")
        return

    # Test payload construction
    fields = {
        "project": {"key": "TEST"},
        "issuetype": {"name": "Epic"},
        "summary": "Test Epic",
        status_fid: "Approved" 
    }
    
    print(f"Input fields: {fields}")
    
    payload = svc._to_payload("TEST", fields)
    
    print(f"Generated Payload: {json.dumps(payload, indent=2)}")
    
    # Check if status was mapped to href
    mapped_val = payload.get(status_fid)
    print(f"Mapped Status Value: {mapped_val}")
    
    if isinstance(mapped_val, dict) and "href" in mapped_val:
        print("SUCCESS: Status mapped to href")
    else:
        print("FAILURE: Status NOT mapped to href")

if __name__ == "__main__":
    test_status_mapping()
