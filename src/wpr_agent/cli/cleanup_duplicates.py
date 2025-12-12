import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from typing import List, Dict, Any

from dotenv import load_dotenv

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Cleanup duplicate Epics in OpenProject based on WPR Order ID.")
    parser.add_argument("--projects", nargs="+", default=["FlowOne", "Session Border Controller", "NIAM", "NM"], help="List of project keys to scan")
    parser.add_argument("--field-id", default="customField2", help="The Custom Field ID for WPR Order ID (default: customField2)")
    parser.add_argument("--delete", action="store_true", help="Actually delete duplicates. If not set, runs in dry-run mode.")
    args = parser.parse_args()

    load_dotenv()
    
    svc = OpenProjectServiceV2()
    order_fid = args.field_id
    
    logger.info(f"Starting Duplicate Cleanup. Mode: {'DELETE' if args.delete else 'DRY-RUN'}")
    logger.info(f"Scanning Projects: {args.projects}")
    logger.info(f"Using Order ID Field: {order_fid}")

    total_deleted = 0
    total_duplicates = 0

    for pkey in args.projects:
        pid = svc._project_id(pkey)
        if not pid:
            logger.warning(f"Project {pkey} not found. Skipping.")
            continue
        
        logger.info(f"Scanning Project: {pkey}...")

        # Fetch all Epics
        tid = svc._type_id(pkey, "Epic")
        if not tid:
             logger.warning(f"Epic type not found in {pkey}. Skipping.")
             continue

        filters = [
            {"project": {"operator": "=", "values": [pid]}},
            {"type": {"operator": "=", "values": [tid]}},
        ]
        
        all_epics = []
        page = 1
        while True:
            try:
                f_str = json.dumps(filters)
                endpoint = f"/api/v3/work_packages?filters={f_str}&pageSize=100&offset={page}"
                resp = svc.client._request("GET", endpoint)
                
                if resp.status_code != 200:
                    logger.error(f"Failed to fetch page {page}: {resp.status_code}")
                    break
                    
                data = resp.json()
                elems = data.get("_embedded", {}).get("elements", [])
                if not elems:
                    break
                    
                all_epics.extend(elems)
                if len(elems) < 100:
                    break
                page += 1
            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break
            
        logger.info(f"  Found {len(all_epics)} Epics in {pkey}.")
        
        # Group by Order ID
        seen = defaultdict(list)
        for e in all_epics:
            oid = e.get(order_fid)
            if oid:
                seen[str(oid)].append(e)
                
        # Process Duplicates
        project_dupes = 0
        for oid, epics in seen.items():
            if len(epics) > 1:
                project_dupes += len(epics) - 1
                # Sort by ID descending (assuming higher ID = newer)
                epics.sort(key=lambda x: x["id"], reverse=True)
                
                keep = epics[0]
                remove = epics[1:]
                
                logger.info(f"  Order {oid}: Keeping {keep['id']}, Found {len(remove)} duplicates: {[e['id'] for e in remove]}")
                
                if args.delete:
                    for e in remove:
                        try:
                            del_endpoint = f"/api/v3/work_packages/{e['id']}"
                            r = svc.client._request("DELETE", del_endpoint)
                            if r.status_code in (200, 204):
                                logger.info(f"    Deleted {e['id']}")
                                total_deleted += 1
                            else:
                                logger.error(f"    Failed to delete {e['id']}: {r.status_code} - {r.text}")
                        except Exception as ex:
                            logger.error(f"    Error deleting {e['id']}: {ex}")
        
        total_duplicates += project_dupes
        logger.info(f"  Project {pkey} Epics Summary: {project_dupes} duplicates found.")

        # --- Story Cleanup ---
        logger.info(f"Scanning Project {pkey} for duplicate Stories...")
        tid_story = svc._type_id(pkey, "Story") or svc._type_id(pkey, "User Story")
        if not tid_story:
             logger.warning(f"Story type not found in {pkey}. Skipping Stories.")
             continue

        filters_story = [
            {"project": {"operator": "=", "values": [pid]}},
            {"type": {"operator": "=", "values": [tid_story]}},
        ]
        
        all_stories = []
        page = 1
        while True:
            try:
                f_str = json.dumps(filters_story)
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
        
        logger.info(f"  Found {len(all_stories)} Stories in {pkey}.")
        
        # Group Stories by OrderID + Subject
        seen_stories = defaultdict(list)
        for s in all_stories:
            oid = s.get(order_fid)
            subj = s.get("subject")
            if oid and subj:
                key = f"{oid}::{subj}"
                seen_stories[key].append(s)
        
        story_dupes = 0
        for key, stories in seen_stories.items():
            if len(stories) > 1:
                story_dupes += len(stories) - 1
                # Sort by ID descending (keep newest)
                stories.sort(key=lambda x: x["id"], reverse=True)
                keep = stories[0]
                remove = stories[1:]
                
                logger.info(f"  Story {key}: Keeping {keep['id']}, Found {len(remove)} duplicates: {[s['id'] for s in remove]}")
                
                if args.delete:
                    for s in remove:
                        try:
                            del_endpoint = f"/api/v3/work_packages/{s['id']}"
                            r = svc.client._request("DELETE", del_endpoint)
                            if r.status_code in (200, 204):
                                logger.info(f"    Deleted Story {s['id']}")
                                total_deleted += 1
                            else:
                                logger.error(f"    Failed to delete Story {s['id']}: {r.status_code}")
                        except Exception as ex:
                            logger.error(f"    Error deleting Story {s['id']}: {ex}")

        total_duplicates += story_dupes
        logger.info(f"  Project {pkey} Stories Summary: {story_dupes} duplicates found.")

    logger.info("-" * 40)
    logger.info(f"Cleanup Complete.")
    logger.info(f"Total Duplicates Found: {total_duplicates}")
    if args.delete:
        logger.info(f"Total Deleted: {total_deleted}")
    else:
        logger.info(f"Total Deleted: 0 (Dry Run)")

if __name__ == "__main__":
    main()
