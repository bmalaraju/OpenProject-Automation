from __future__ import annotations

"""
CLI Autopilot for wpr_agent — orchestrates preflight and delegates to the router.

Usage example:
  python wpr_agent/agent.py \
    --file C:\\path\\work_packages.xlsx \
    --sheet Sheet1 \
    --registry wpr_agent/config/domain_project_registry.json \
    --online --dry-run \
    --domains IPTEL \
    --artifact-dir artifacts/canary \
    --report artifacts/canary/run_report.json \
    --summary artifacts/canary/summary.txt \
    --provision --provision-profile wpr_agent/profiles/wpr_profile.min.json

Notes
 - Prefers reusing the existing router CLI implementation; no graph code here.
 - Performs light preflight checks and passes through flags to router.
 - Does not mutate configuration or secrets.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load env from wpr_agent/.env first, then optionally root .env
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(REPO_ROOT / ".env", override=False)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Agent Autopilot: preflight + router orchestration")
    ap.add_argument("--file", required=True, help="Path to WPR Excel input")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--registry", required=True, help="Path to Domain->Project registry JSON")

    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--online", action="store_true")
    ap.add_argument("--dry-run", action="store_true")

    ap.add_argument("--domains", help="Comma-separated raw domain filter list (e.g., IPTEL,DS&C Analytics)")
    ap.add_argument("--continue-on-error", action="store_true")
    ap.add_argument("--domain-concurrency", type=int, default=1)
    ap.add_argument("--llm", action="store_true", help="Enable LLM summary (if OPENAI_API_KEY present)")

    ap.add_argument("--provision", action="store_true", help="Run provisioning pre-pass per mapped project before compile (admin-optional)")
    ap.add_argument("--provision-apply", action="store_true", help="Apply provisioning changes (otherwise preview-only)")
    ap.add_argument("--provision-profile", help="Provisioning profile JSON (defaults to wpr_agent/profiles/wpr_profile.min.json when omitted)")

    ap.add_argument("--artifact-dir")
    ap.add_argument("--report")
    ap.add_argument("--summary")

    return ap.parse_args()


def _fail(msg: str, code: int = 2) -> int:
    print(f"input_error: {msg}")
    return code


def _preflight(ns: argparse.Namespace) -> int:
    # Check files
    if not os.path.exists(ns.file):
        return _fail(f"Excel file not found: {ns.file}")
    if not os.path.exists(ns.registry):
        return _fail(f"Registry JSON not found: {ns.registry}")
    # Optional artifact/report directories
    try:
        if ns.artifact_dir:
            Path(ns.artifact_dir).mkdir(parents=True, exist_ok=True)
        if ns.report:
            Path(ns.report).parent.mkdir(parents=True, exist_ok=True)
        if ns.summary:
            Path(ns.summary).parent.mkdir(parents=True, exist_ok=True)
    except Exception as ex:
        return _fail(f"Failed to prepare artifact/report paths: {ex}")
    # Light env checks (do not block offline runs)
    if ns.online:
        # Presence of OAuth env needed for online flows; details are validated at call time
        needed = ["JIRA_OAUTH_CLIENT_ID", "JIRA_OAUTH_CLIENT_SECRET"]
        missing = [k for k in needed if not os.getenv(k)]
        if missing:
            print(f"warn: missing OAuth env vars {missing}; relying on existing tokens/config.")
    return 0


def _build_router_argv(ns: argparse.Namespace) -> List[str]:
    argv: List[str] = [
        "--file", ns.file,
        "--sheet", ns.sheet,
        "--registry", ns.registry,
    ]
    if ns.offline:
        argv.append("--offline")
    if ns.online:
        argv.append("--online")
    if ns.dry_run:
        argv.append("--dry-run")
    if ns.domains:
        argv.extend(["--domains", ns.domains])
    if ns.continue_on_error:
        argv.append("--continue-on-error")
    if ns.domain_concurrency and int(ns.domain_concurrency) != 1:
        argv.extend(["--domain-concurrency", str(int(ns.domain_concurrency))])
    if ns.llm:
        argv.append("--llm")
    if ns.artifact_dir:
        argv.extend(["--artifact-dir", ns.artifact_dir])
    if ns.report:
        argv.extend(["--report", ns.report])
    if ns.summary:
        argv.extend(["--summary", ns.summary])
    if ns.provision:
        argv.append("--provision")
        if ns.provision_apply:
            argv.append("--provision-apply")
        if ns.provision_profile:
            argv.extend(["--provision-profile", ns.provision_profile])
    return argv


def main() -> int:
    ns = parse_args()
    rc = _preflight(ns)
    if rc != 0:
        return rc

    # Defer to router CLI for orchestration (graph or linear fallback handled there)
    try:
        from wpr_agent.cli import router as router_cli  # type: ignore
    except Exception as ex:
        print(f"router_import_error: {ex}")
        return 4

    argv = _build_router_argv(ns)
    try:
        code = router_cli.main(argv)
    except SystemExit as se:
        code = int(se.code) if isinstance(se.code, int) else 4
    except Exception as ex:
        print(f"router_run_error: {ex}")
        code = 4
    return int(code or 0)


if __name__ == "__main__":
    sys.exit(main())
