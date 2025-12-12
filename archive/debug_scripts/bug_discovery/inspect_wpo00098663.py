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
order_id = "WPO00098663"

print(f"Listing all WPs in project {project_key}...")
pid = svc._project_id(project_key)
wps = svc.client._get_paginated(f"/api/v3/projects/{pid}/work_packages")

matches = []
for wp in wps:
    # Check customField2 (Order ID)
    cf2 = wp.get("customField2")
    if cf2 == order_id:
        matches.append(wp)
    elif order_id in wp.get("subject", ""):
        matches.append(wp)

print(f"Found {len(matches)} matching Epics/Stories.")

for wp in matches:
    print(f"\nID: {wp.get('id')}")
    print(f"Subject: {wp.get('subject')}")
    print(f"Type: {wp.get('_links', {}).get('type', {}).get('title')}")
    parent = wp.get("_links", {}).get("parent", {}).get("href")
    print(f"Parent: {parent}")
    print("Custom Fields:")
    print(f"  Order ID (customField2): {wp.get('customField2')}")
