import json
import os
import sys
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2
from dotenv import load_dotenv

def main():
    load_dotenv()
    
    # Load registry
    reg_path = "config/product_project_registry.json"
    if not os.path.exists(reg_path):
        print(f"Registry not found at {reg_path}")
        return

    with open(reg_path, "r") as f:
        reg = json.load(f)
    
    # Get unique project keys from registry values
    projects = set(reg.get("registry", {}).values())
    
    print(f"Found projects to clean: {projects}")
    
    svc = OpenProjectServiceV2()
    
    for proj_key in projects:
        print(f"\nProcessing project: {proj_key}")
        pid = svc._project_id(proj_key)
        if not pid:
            print(f"  Project '{proj_key}' not found or not accessible, skipping.")
            continue
            
        print(f"  Resolved Project ID: {pid}")
        
        # Fetch all WPs for this project
        # We filter by project ID
        filters = [{"project": {"operator": "=", "values": [pid]}}]
        filt_str = json.dumps(filters)
        
        print(f"  Starting deletion loop for project {proj_key}...")
        
        total_deleted = 0
        while True:
            # Fetch a batch of WPs (page size 50)
            # We don't use pagination offset because we are deleting them!
            # So always fetch page 1.
            try:
                # We use the raw request to control pagination explicitly
                # filters is already json string
                r = svc.client._request("GET", "/api/v3/work_packages", params={"filters": filt_str, "pageSize": 50, "offset": 1})
                if r.status_code != 200:
                    print(f"  Error fetching batch: {r.status_code} {r.text}")
                    break
                    
                data = r.json() or {}
                elems = ((data.get("_embedded") or {}).get("elements") or [])
                
                if not elems:
                    print("  No more work packages found.")
                    break
                    
                print(f"  Fetched batch of {len(elems)} items. Deleting...")
                
                batch_deleted = 0
                for wp in elems:
                    wp_id = wp.get("id")
                    try:
                        del_r = svc.client._request("DELETE", f"/api/v3/work_packages/{wp_id}")
                        if del_r.status_code in (200, 204):
                            batch_deleted += 1
                            total_deleted += 1
                        elif del_r.status_code == 404:
                            # Already deleted (maybe cascade)
                            pass
                        else:
                            print(f"    Failed to delete WP {wp_id}: {del_r.status_code}")
                    except Exception as e:
                        print(f"    Exception deleting WP {wp_id}: {e}")
                
                print(f"  Batch complete. Total deleted so far: {total_deleted}")
                
                # Safety break if we are not making progress?
                # If we fetched 50 items and deleted 0, we might be stuck.
                if batch_deleted == 0 and len(elems) > 0:
                     # Check if they are actually still there?
                     # If we failed to delete them, we will loop forever.
                     print("  Warning: Fetched items but failed to delete any. Aborting to prevent infinite loop.")
                     break
                     
            except Exception as e:
                print(f"  Critical error in loop: {e}")
                break

        print(f"  Finished project {proj_key}. Total deleted: {total_deleted}")

if __name__ == "__main__":
    main()
