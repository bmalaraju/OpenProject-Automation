import os
import sys
import json
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2
from dotenv import load_dotenv

def main():
    load_dotenv()
    svc = OpenProjectServiceV2()
    
    # Pick a likely deleted ID. The cleanup script deleted thousands.
    # Let's try a random one or one seen in logs.
    # The logs showed 9862, 9863 etc were deleted.
    wp_id = "9862" 
    
    print(f"Attempting to update deleted WP {wp_id}...")
    
    payload = {"lockVersion": 1, "subject": "Updated Subject"}
    
    try:
        status, body = svc.client.update_work_package(wp_id, payload)
        print(f"Status: {status}")
        print(f"Body: {json.dumps(body, indent=2)}")
        
        # Check if our detection logic works
        ident = str(body.get("errorIdentifier") or "")
        msg = str(body.get("message") or "")
        is_not_found = (
            "NotFound" in ident or "not be found" in msg or "deleted" in msg
        )
        print(f"Detected as NotFound? {is_not_found}")
        
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    main()
