"""
Test custom field discovery
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

from wpr_agent.services.provider import make_service

svc = make_service()

# Check what _cf_map returns
cf = svc._cf_map()
print(f"Custom fields from _cf_map(): {len(cf)} fields")
for k, v in sorted(cf.items())[:5]:
    print(f"  {k!r}: {v}")

# Check what discover_fieldmap returns
fieldmap = svc.discover_fieldmap("FlowOne")
print(f"\nDiscovered custom fields: {len(fieldmap.discovered_custom_fields)} fields")
for k, v in sorted(fieldmap.discovered_custom_fields.items())[:5]:
    print(f"  {k!r}: {v}")
