from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load env: prefer root .env, allow wpr_agent/.env to overlay
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

from wpr_agent.services.provider import make_service


def main() -> None:
    project_key = os.getenv("JIRA_PROJECT_KEY", "").strip()
    if not project_key:
        print("JIRA_PROJECT_KEY not set (check your .env)")
        raise SystemExit(1)

    svc = make_service()
    access = svc.check_access(project_key)
    print(json.dumps(access, indent=2))


if __name__ == "__main__":
    main()

