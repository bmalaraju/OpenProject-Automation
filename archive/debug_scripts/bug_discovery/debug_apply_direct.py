import os
import sys
import uuid
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from dotenv import load_dotenv
load_dotenv()

# Force disable MCP for this script to ensure local execution
os.environ["MCP_OP_TRANSPORT"] = ""
os.environ["MCP_JIRA_TRANSPORT"] = ""
os.environ["FORCE_OP_SYNC"] = "1"

from wpr_agent.cli.apply_plan import apply_bp
from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2
from wpr_agent.models import TrackerFieldMap

def main():
    print("DEBUG: Starting direct apply_bp test...")
    
    svc = OpenProjectServiceV2()
    
    # Mock data simulating a deleted item
    # We use a random ID/Name to avoid messing with real data if it accidentally works
    run_id = str(uuid.uuid4())[:8]
    bp_id = f"WPO-TEST-{run_id}"
    
    print(f"DEBUG: Testing with BP ID {bp_id}")
    
    # Construct a minimal plan
    bp_plan = {
        "bp_id": bp_id,
        "project_name": "NIAM",
        "product": "NIAM",
        "domain": "NIAM",
        "customer": "Test Customer",
        "epic": {
            "plan": {
                "order_id": bp_id,
                "summary": f"Test Epic {bp_id}",
                "description_adf": {"content": [{"content": [{"text": "Test Description", "type": "text"}], "type": "paragraph"}], "type": "doc"},
                "stories": [
                    {
                        "order_id": f"{bp_id}-1",
                        "summary": f"Test Story {bp_id}-1",
                        "description_adf": {"content": [{"content": [{"text": "Test Story Desc", "type": "text"}], "type": "paragraph"}], "type": "doc"},
                        "fields": {}
                    }
                ]
            }
        }
    }
    
    fieldmap = TrackerFieldMap(
        epic_link_field_id=None,
        epic_name_field_id=None,
        start_date_supported=True,
        required_fields_by_type={},
        discovered_custom_fields={}
    )
    
    print("DEBUG: Calling apply_bp...")
    try:
        created, warns, errs, stats, timings = apply_bp(
            svc=svc,
            bundle_domain="NIAM",
            project_key="NIAM",
            fieldmap=fieldmap,
            bp_plan=bp_plan,
            max_retries=1,
            backoff_base=0.1,
            dry_run=False
        )
        
        print("\n=== Result ===")
        print(f"Created: {created}")
        print(f"Warnings: {warns}")
        print(f"Errors: {errs}")
        print(f"Stats: {stats}")
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
