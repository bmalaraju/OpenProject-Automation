from __future__ import annotations

"""
Switch Jira base_url between site and aggregator.

Usage:
  python wpr_agent/scripts/switch_base.py --site https://adithya-pocs.atlassian.net
  python wpr_agent/scripts/switch_base.py --aggregator 5fc0c58e-2ee5-4804-bb23-7113c4fd338a

Edits wpr_agent/config/working_jira_config.json in-place.
"""

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--site", help="Site base (https://<site>.atlassian.net)")
    g.add_argument("--aggregator", help="Cloud ID for aggregator base (api.atlassian.com/ex/jira/<id>)")
    ap.add_argument("--config", default="wpr_agent/config/working_jira_config.json")
    args = ap.parse_args()

    p = Path(args.config)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    if args.site:
        base = args.site.rstrip("/")
    else:
        cloud_id = args.aggregator.strip()
        base = f"https://api.atlassian.com/ex/jira/{cloud_id}"
    data["base_url"] = base
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "base_url": base, "config": str(p)}, indent=2))


if __name__ == "__main__":
    main()

