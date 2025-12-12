import sys
import os
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.append('src')

from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2

def main():
    service = OpenProjectServiceV2()
    print("Searching for an Epic...")
    # Try to find *any* epic. We'll just list some.
    # We can use client directly.
    client = service.client
    
    # Search for type Epic
    # We need project ID first. Let's list projects.
    projects = client.list_projects()
    if not projects:
        print("No projects found.")
        return

    project = projects[0]
    pid = project['id']
    print(f"Using project: {project['name']} ({pid})")

    # Find Epic type ID
    types = client.list_types_for_project(pid)
    epic_type = types.get('epic')
    if not epic_type:
        print("Epic type not found in project.")
        # Try to find any WP
        filters = [{"project": {"operator": "=", "values": [str(pid)]}}]
    else:
        tid = epic_type['id']
        filters = [
            {"project": {"operator": "=", "values": [str(pid)]}},
            {"type": {"operator": "=", "values": [str(tid)]}}
        ]

    wps = client.search_work_packages(filters, page_size=1)
    if not wps:
        print("No work packages found.")
        return

    wp = wps[0]
    wp_id = wp['id']
    print(f"Found WP: {wp['subject']} ({wp_id})")

    # Fetch activities
    print(f"Fetching activities for WP {wp_id}...")
    # /api/v3/work_packages/{id}/activities
    resp = client._request("GET", f"/api/v3/work_packages/{wp_id}/activities")
    if resp.status_code != 200:
        print(f"Failed to fetch activities: {resp.status_code}")
        print(resp.text)
        return

    activities = resp.json()
    # Print structure of first activity that has a status change
    embedded = activities.get('_embedded', {})
    elements = embedded.get('elements', [])
    
    print(f"Found {len(elements)} activities.")
    
    for activity in elements:
        details = activity.get('details', [])
        # Check if 'status' is in details (it might be a list of changes)
        # Actually details is usually a list of objects describing changes?
        # Let's inspect the raw 'details' to see how status change is represented.
        # It might be in 'details' object if it's a dict, or list.
        # OpenProject API v3: details is a collection of changes.
        
        # Let's dump the first activity to see structure
        print(json.dumps(activity, indent=2))
        break

if __name__ == "__main__":
    main()
