from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import load_dotenv

# Bootstrap env and paths
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wpr_agent.tools.excel_tools import (
    ensure_columns,
    group_by_bp,
    group_by_domain_then_bp,
    epic_summary,
    epic_meta,
    story_core,
    story_summary,
    epic_description_adf,
    story_description_adf,
)
from wpr_agent.services.provider import make_service
from wpr_agent.config.domain_registry import load_registry, normalize_domain


def main() -> None:
    ap = argparse.ArgumentParser(description="Import WPR Excel and create Epic/Story hierarchy (sub-tasks commented out). Domain→BP routing supported via registry.")
    ap.add_argument("--file", "-f", required=True)
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--project", "-p", required=False, help="If set, route all rows to this single Jira project key (legacy behavior).")
    ap.add_argument("--registry", default=str(BASE_DIR / "config" / "domain_project_registry.json"), help="Path to Domain→Project registry JSON.")
    ap.add_argument("--upsert", action="store_true", help="Use find-or-create and update-in-place behavior (Step 5 upsert).")
    ap.add_argument("--max-retries", type=int, default=3, help="Max retries for transient errors (Step 6).")
    ap.add_argument("--backoff-base", type=float, default=0.5, help="Base seconds for exponential backoff (Step 6).")
    args = ap.parse_args()

    svc = None
    reg = load_registry(Path(args.registry))

    # Read Excel
    try:
        df = pd.read_excel(args.file, sheet_name=args.sheet, engine="openpyxl").fillna("")
    except Exception as ex:
        print(json.dumps({"error": f"Failed to read Excel: {ex}"}, indent=2))
        raise SystemExit(1)

    df = ensure_columns(df)

    created: Dict[str, Any] = {"epics": [], "stories": [], "errors": [], "warnings": [], "updated": [], "stats": {"retries": 0, "dropped_assignees": 0}}

    # Track stories per epic to build direct links back on epic
    epic_to_story_urls: Dict[str, List[str]] = {}

    # Legacy single-project flow when --project provided
    if args.project:
        if svc is None:
            svc = make_service()
        access = svc.check_access(args.project)
        if not access.get("ok"):
            print(json.dumps({"error": "Insufficient Jira access", "details": access}, indent=2))
            raise SystemExit(1)
        svc.discover_fields(args.project)

        for bp_id, group in group_by_bp(df):
            row0 = group.iloc[0].to_dict()
            meta = epic_meta(row0)
            ep_summary = epic_summary(meta["project_name"], bp_id)

            # Upsert Epic (find or create)
            epic_key = None
            if args.upsert:
                try:
                    ex_epic = svc.find_epic_by_summary(args.project, ep_summary)
                    if ex_epic:
                        epic_key = ex_epic.get("key")
                        planned = svc.build_epic_fields(args.project, ep_summary, epic_description_adf(meta, wp_links=[]))
                        diff = svc.compute_epic_diff(planned, ex_epic.get("fields", {}) or {})
                        if diff:
                            _ = svc.update_issue(epic_key, diff)
                except Exception as ex:
                    created["errors"].append({"bp_id": bp_id, "error": f"epic find/update failed: {ex}"})
            if not epic_key:
                ep_fields = svc.build_epic_fields(args.project, ep_summary, epic_description_adf(meta, wp_links=[]))
                ok, res, retries_used, dropped = svc.create_issue_resilient(
                    ep_fields, max_retries=args.max_retries, backoff_base=args.backoff_base
                )
                created["stats"]["retries"] += retries_used
                if dropped:
                    created["stats"]["dropped_assignees"] += 1
                if not ok:
                    created["errors"].append({"bp_id": bp_id, "error": res})
                    continue
                epic_key = res.get("key")
                created["epics"].append(epic_key)
            epic_to_story_urls[epic_key] = []

            # Upsert Stories for each row
            for _, r in group.iterrows():
                row = r.to_dict()
                core = story_core(row)
                st_summary = story_summary(core)
                acct = svc.resolve_account_id(core.get("employee_name", "")) if core.get("employee_name") else None
                st_desc = story_description_adf(row)
                st_fields = svc.build_story_fields(
                    args.project,
                    summary=st_summary,
                    description_adf=st_desc,
                    due_date=core.get("due_date") or None,
                    assignee_account_id=acct,
                    epic_key=epic_key,
                )
                story_key = None
                if args.upsert:
                    try:
                        ex_story = svc.find_story_by_summary(args.project, st_summary)
                        if ex_story:
                            story_key = ex_story.get("key")
                            diff = svc.compute_story_diff(st_fields, ex_story.get("fields", {}) or {})
                            if diff:
                                ok, resu, retries_used, dropped = svc.update_issue_resilient(
                                    story_key, diff, max_retries=args.max_retries, backoff_base=args.backoff_base
                                )
                                created["stats"]["retries"] += retries_used
                                if dropped:
                                    created["stats"]["dropped_assignees"] += 1
                                if ok:
                                    created["updated"].append(story_key)
                            try:
                                link = svc.story_browse_url("", story_key)
                            except Exception:
                                link = f"/browse/{story_key}"
                            epic_to_story_urls[epic_key].append(link)
                    except Exception as ex:
                        created["errors"].append({"bp_id": bp_id, "wp_id": core.get("wp_id"), "error": f"story find/update failed: {ex}"})
                if not story_key:
                    ok, res, retries_used, dropped = svc.create_issue_resilient(
                        st_fields, max_retries=args.max_retries, backoff_base=args.backoff_base
                    )
                    created["stats"]["retries"] += retries_used
                    if dropped:
                        created["stats"]["dropped_assignees"] += 1
                    if not ok:
                        created["errors"].append({"bp_id": bp_id, "wp_id": core.get("wp_id"), "error": res})
                        continue
                    story_key = res.get("key")
                    created["stories"].append(story_key)
                    try:
                        link = svc.story_browse_url("", story_key)
                    except Exception:
                        link = f"/browse/{story_key}"
                    epic_to_story_urls[epic_key].append(link)

            # Update Epic description with direct links to created Stories
            links = epic_to_story_urls.get(epic_key, [])
            ep_desc = epic_description_adf(meta, links)
            ok, res, retries_used, dropped = svc.update_issue_resilient(
                epic_key, {"description": ep_desc}, max_retries=args.max_retries, backoff_base=args.backoff_base, allow_assignee_fallback=False
            )
            created["stats"]["retries"] += retries_used
            if not ok:
                created["warnings"].append({"epic": epic_key, "warn": "Epic description update failed", "details": res})

        print(json.dumps(created, indent=2))
        return

    # Domain→BP multi-project flow via registry
    # Cache discovery per project
    discovered_projects: Dict[str, bool] = {}

    for dom_val, bp_groups in group_by_domain_then_bp(df):
        norm = normalize_domain(dom_val)
        project_key = reg.get(norm, "")
        if not project_key:
            created["warnings"].append(
                f"No project mapping for domain '{dom_val}' (normalized '{norm}'). Skipping this domain group."
            )
            continue

        if project_key not in discovered_projects:
            if svc is None:
                svc = make_service()
            access = svc.check_access(project_key)
            if not access.get("ok"):
                created["errors"].append({"domain": dom_val, "project": project_key, "error": "Insufficient Jira access"})
                continue
            svc.discover_fields(project_key)
            discovered_projects[project_key] = True

        for bp_id, group in bp_groups:
            row0 = group.iloc[0].to_dict()
            meta = epic_meta(row0)
            ep_summary = epic_summary(meta["project_name"], bp_id)
            # Upsert Epic (find or create)
            epic_key = None
            if args.upsert:
                try:
                    ex_epic = svc.find_epic_by_summary(project_key, ep_summary)
                    if ex_epic:
                        epic_key = ex_epic.get("key")
                        planned = svc.build_epic_fields(project_key, ep_summary, epic_description_adf(meta, wp_links=[]))
                        diff = svc.compute_epic_diff(planned, ex_epic.get("fields", {}) or {})
                        if diff:
                            _ = svc.update_issue(epic_key, diff)
                except Exception as ex:
                    created["errors"].append({"domain": dom_val, "bp_id": bp_id, "project": project_key, "error": f"epic find/update failed: {ex}"})
            if not epic_key:
                ep_fields = svc.build_epic_fields(project_key, ep_summary, epic_description_adf(meta, wp_links=[]))
                ok, res, retries_used, dropped = svc.create_issue_resilient(
                    ep_fields, max_retries=args.max_retries, backoff_base=args.backoff_base
                )
                created["stats"]["retries"] += retries_used
                if dropped:
                    created["stats"]["dropped_assignees"] += 1
                if not ok:
                    created["errors"].append({"domain": dom_val, "bp_id": bp_id, "project": project_key, "error": res})
                    continue
                epic_key = res.get("key")
                created["epics"].append(epic_key)
            epic_to_story_urls[epic_key] = []

            for _, r in group.iterrows():
                row = r.to_dict()
                core = story_core(row)
                st_summary = story_summary(core)
                acct = svc.resolve_account_id(core.get("employee_name", "")) if core.get("employee_name") else None
                st_desc = story_description_adf(row)
                st_fields = svc.build_story_fields(
                    project_key,
                    summary=st_summary,
                    description_adf=st_desc,
                    due_date=core.get("due_date") or None,
                    assignee_account_id=acct,
                    epic_key=epic_key,
                )
                story_key = None
                if args.upsert:
                    try:
                        ex_story = svc.find_story_by_summary(project_key, st_summary)
                        if ex_story:
                            story_key = ex_story.get("key")
                            diff = svc.compute_story_diff(st_fields, ex_story.get("fields", {}) or {})
                            if diff:
                                ok, resu, retries_used, dropped = svc.update_issue_resilient(
                                    story_key, diff, max_retries=args.max_retries, backoff_base=args.backoff_base
                                )
                                created["stats"]["retries"] += retries_used
                                if dropped:
                                    created["stats"]["dropped_assignees"] += 1
                                if ok:
                                    created["updated"].append(story_key)
                            try:
                                link = svc.story_browse_url("", story_key)
                            except Exception:
                                link = f"/browse/{story_key}"
                            epic_to_story_urls[epic_key].append(link)
                    except Exception as ex:
                        created["errors"].append({"domain": dom_val, "bp_id": bp_id, "wp_id": core.get("wp_id"), "project": project_key, "error": f"story find/update failed: {ex}"})
                if not story_key:
                    ok, res, retries_used, dropped = svc.create_issue_resilient(
                        st_fields, max_retries=args.max_retries, backoff_base=args.backoff_base
                    )
                    created["stats"]["retries"] += retries_used
                    if dropped:
                        created["stats"]["dropped_assignees"] += 1
                    if not ok:
                        created["errors"].append({"domain": dom_val, "bp_id": bp_id, "wp_id": core.get("wp_id"), "project": project_key, "error": res})
                        continue
                    story_key = res.get("key")
                    created["stories"].append(story_key)
                    try:
                        link = svc.story_browse_url("", story_key)
                    except Exception:
                        link = f"/browse/{story_key}"
                    epic_to_story_urls[epic_key].append(link)

            # Update Epic description with direct links
            links = epic_to_story_urls.get(epic_key, [])
            ep_desc = epic_description_adf(meta, links)
            ok, res, retries_used, dropped = svc.update_issue_resilient(
                epic_key, {"description": ep_desc}, max_retries=args.max_retries, backoff_base=args.backoff_base, allow_assignee_fallback=False
            )
            created["stats"]["retries"] += retries_used
            if not ok:
                created["warnings"].append({"epic": epic_key, "project": project_key, "warn": "Epic description update failed", "details": res})

    print(json.dumps(created, indent=2))


if __name__ == "__main__":
    main()
