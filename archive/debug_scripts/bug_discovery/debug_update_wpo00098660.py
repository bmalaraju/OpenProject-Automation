import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2

# Set env vars
field_map_path = Path("config/op_field_id_overrides.json").resolve()
custom_options_path = Path("config/op_custom_option_overrides.json").resolve()
os.environ["OP_FIELD_ID_OVERRIDES_PATH"] = str(field_map_path)
os.environ["OP_CUSTOM_OPTION_OVERRIDES_PATH"] = str(custom_options_path)

print("Initializing OpenProjectServiceV2...")
svc = OpenProjectServiceV2()

project_key = "FlowOne" # or "Flow One"
order_id = "WPO00098660"

print(f"Listing all WPs in project {project_key}...")
pid = svc._project_id(project_key)
if not pid:
    print("Project ID not found.")
    sys.exit(1)

wps = svc.client._get_paginated(f"/api/v3/projects/{pid}/work_packages")
print(f"Found {len(wps)} WPs.")

epic = None
for wp in wps:
    s = wp.get("subject", "")
    if order_id in s:
        print(f"Found match: {s} (ID: {wp.get('id')})")
        epic = {"key": str(wp.get("id")), "fields": wp}
        break

if not epic:
    print("Epic not found in list.")
    sys.exit(1)

print(f"Found Epic: {epic['key']}")
print("Current Fields:")
print(json.dumps(epic['fields'], indent=2))

# Simulate planned fields (simplified)
planned_fields = {
    "project": {"key": project_key},
    "issuetype": {"name": "Epic"},
    "summary": f"Flow One :: {order_id}",
    "customField10": "Approved", # WPR WP Order Status
    "customField22": "2023-07-26", # WPR Updated Date
}

print("Planned Fields:")
print(json.dumps(planned_fields, indent=2))

print("Computing Diff...")
diff = svc.compute_epic_diff(planned_fields, epic['fields'])
print("Diff:")
print(json.dumps(diff, indent=2))

if not diff:
    print("No diff computed.")
else:
    print("Attempting Update...")
    # Merge diff into fields for update (simulating backfill logic)
    update_fields = {**diff, "project": {"key": project_key}}
    
    # Manually call _to_payload to see what would be sent
    payload = svc._to_payload(project_key, update_fields)
    print("Generated Payload:")
    print(json.dumps(payload, indent=2))
    
    # Try update
    ok, res, _, _ = svc.update_issue_resilient(epic['key'], update_fields)
    if ok:
        print("Update SUCCESS.")
    else:
        print("Update FAILED.")
        print(res)
