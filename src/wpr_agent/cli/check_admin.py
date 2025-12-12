from __future__ import annotations

"""
Check admin capability for a Jira project (prints /mypermissions summary).

Usage:
  python wpr_agent/scripts/check_admin.py --project ECS

Output:
  {
    "project": "ECS",
    "has_admin": true,
    "permissions_true": ["ADMINISTER_PROJECTS", ...]
  }
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Bootstrap env and paths similar to other scripts
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wpr_agent.services.jira_provisioning import JiraProvisioningService
from wp_jira_agent.jira import JiraClient  # type: ignore


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Check Jira admin permissions for a project")
    ap.add_argument("--project", required=True, help="Jira project key (e.g., ECS)")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    svc = JiraProvisioningService()
    ok = svc.has_admin(args.project)
    # Also fetch the raw permissions to help debug scopes
    client = JiraClient()
    try:
        r = client._request(
            "GET",
            "/rest/api/3/mypermissions",
            params={
                "projectKey": args.project,
                "permissions": "ADMINISTER_PROJECTS,ADMINISTER",
            },
        )
        perms_raw: Dict[str, Any] = r.json() if r.status_code == 200 else {}
    except Exception:
        perms_raw = {}
    perms_true: List[str] = []
    for k, v in (perms_raw.get("permissions") or {}).items():
        try:
            if isinstance(v, dict) and v.get("havePermission") is True:
                perms_true.append(k)
        except Exception:
            continue
    out = {
        "project": args.project,
        "has_admin": ok,
        "permissions_true": sorted(perms_true),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
