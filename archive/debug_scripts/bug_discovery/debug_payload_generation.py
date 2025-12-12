import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2

# Set env vars as backfill.py does
field_map_path = Path("config/op_field_id_overrides.json").resolve()
custom_options_path = Path("config/op_custom_option_overrides.json").resolve()
os.environ["OP_FIELD_ID_OVERRIDES_PATH"] = str(field_map_path)
os.environ["OP_CUSTOM_OPTION_OVERRIDES_PATH"] = str(custom_options_path)

print(f"Overrides Path: {os.environ['OP_CUSTOM_OPTION_OVERRIDES_PATH']}")

print("Initializing OpenProjectServiceV2...")
svc = OpenProjectServiceV2()

project_key = "FlowOne" # or "Flow One"
issue_type = "Epic"
status_value = "Approved"

print("Testing _to_payload logic...")
fields = {
    "project": {"key": project_key},
    "issuetype": {"name": issue_type},
    "customField10": status_value
}
payload = svc._to_payload(project_key, fields)
print("Generated Payload for customField10:")
val = payload.get("customField10")
print(json.dumps(val, indent=2))

if isinstance(val, dict) and "href" in val:
    print("SUCCESS: Mapped to href.")
else:
    print("FAILURE: Did not map to href.")
