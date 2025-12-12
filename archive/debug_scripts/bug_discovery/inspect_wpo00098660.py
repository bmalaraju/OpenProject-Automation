import sys
import json
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2

# Ensure config paths are set
field_map_path = Path("config/op_field_id_overrides.json").resolve()
custom_options_path = Path("config/op_custom_option_overrides.json").resolve()
os.environ["OP_FIELD_ID_OVERRIDES_PATH"] = str(field_map_path)
os.environ["OP_CUSTOM_OPTION_OVERRIDES_PATH"] = str(custom_options_path)

svc = OpenProjectServiceV2()
project_key = "FlowOne"
order_id = "WPO00098660"

print(f"Listing all Epics in project {project_key}...")
pid = svc._project_id(project_key)
# Filter for Epics (type ID 33 usually, but let's fetch all and filter by type name)
wps = svc.client._get_paginated(f"/api/v3/projects/{pid}/work_packages")

matches = []
for wp in wps:
    t = wp.get("_links", {}).get("type", {}).get("title")
    if t == "Epic":
        matches.append(wp)

print(f"Found {len(matches)} Epics.")
for wp in matches:
    s = wp.get("subject", "")
    if order_id in s:
        print(f"MATCH: {s} (ID: {wp.get('id')})")
    else:
        # Print first few non-matches to verify format
        pass

print(f"Found {len(matches)} matching Epics/Stories.")

for wp in matches:
    print(f"\nID: {wp.get('id')}")
    print(f"Subject: {wp.get('subject')}")
    print(f"Type: {wp.get('_links', {}).get('type', {}).get('title')}")
    print("Custom Fields:")
    print(f"  Order ID (customField2): {wp.get('customField2')}")
    print(f"  Status (customField10): {wp.get('customField10')}")
    print(f"  Updated Date (customField22): {wp.get('customField22')}")
    if wp.get('customField22'):
        print("  -> SUCCESS: Updated Date is populated.")
    else:
        print("  -> FAILURE: Updated Date is missing.")
