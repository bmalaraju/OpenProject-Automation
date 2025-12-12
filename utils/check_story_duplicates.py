import sys
import os
import json
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv()
from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2

svc = OpenProjectServiceV2()
projects = ["FlowOne", "Session Border Controller", "NIAM", "NM"]
# Story Order ID is usually stored in the same field or a different one?
# In backfill.py/apply_plan.py, we saw logic to inject Order ID into Stories too.
# Let's assume customField2 (WPR Order ID) is also used for Stories, or check overrides.
order_fid = "customField2" 

print("Checking for duplicate Stories...")

for pkey in projects:
    pid = svc._project_id(pkey)
    if not pid:
        continue
    
    print(f"Scanning Project: {pkey}...")

    # Fetch all Stories
    tid = svc._type_id(pkey, "Story") # or "User Story"?
    if not tid:
        # Try "User Story" if "Story" fails
        tid = svc._type_id(pkey, "User Story")
    
    if not tid:
        print(f"  Story type not found in {pkey}")
        continue

    filters = [
        {"project": {"operator": "=", "values": [pid]}},
        {"type": {"operator": "=", "values": [tid]}},
    ]
    
    all_stories = []
    page = 1
    while True:
        try:
            f_str = json.dumps(filters)
            endpoint = f"/api/v3/work_packages?filters={f_str}&pageSize=100&offset={page}"
            resp = svc.client._request("GET", endpoint)
            
            if resp.status_code != 200:
                break
                
            data = resp.json()
            elems = data.get("_embedded", {}).get("elements", [])
            if not elems:
                break
                
            all_stories.extend(elems)
            if len(elems) < 100:
                break
            page += 1
        except Exception:
            break
            
    print(f"  Found {len(all_stories)} Stories.")
    
    # Group by Order ID (Stories might share Order ID if they belong to same order? 
    # No, Stories usually have OrderID + Instance or unique summary.
    # But if we have duplicates, they will have identical Order ID + Summary/Subject.
    # Let's group by Subject + Order ID to find true duplicates.
    
    seen = defaultdict(list)
    for s in all_stories:
        oid = s.get(order_fid)
        subject = s.get("subject")
        if oid and subject:
            key = f"{oid}::{subject}"
            seen[key].append(s)
            
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    print(f"  Duplicates found: {len(dupes)} sets")
    if dupes:
        print(f"  Example: {list(dupes.keys())[0]} -> {[s['id'] for s in list(dupes.values())[0]]}")

print("\nDone.")
