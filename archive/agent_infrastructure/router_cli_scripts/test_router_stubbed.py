from __future__ import annotations

"""
Test harness for Router (stubbed-online) — Phase 6 acceptance smoke.

Scenarios:
- Offline dry-run sanity
- Online stub success
- Online stub rate-limit once (retries aggregate)
- Resume checkpoint (skip first BP)

Usage (PowerShell):
  python wpr_agent/scripts/test_router_stubbed.py
"""

import os
from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    td = ROOT / "tmp_router"
    td.mkdir(parents=True, exist_ok=True)
    # Registry
    (td / "registry.json").write_text(json.dumps({"registry": {"CLOUD_INFRA": "TEST"}}, indent=2), encoding="utf-8")
    # Excel
    import pandas as pd

    df = pd.DataFrame([
        {"Domain": "Cloud Infra", "BP ID": "BP-1", "Project Name": "Proj A", "Product": "Prod", "Customer": "Cust", "WP Order ID": "WPO-1", "WP ID": "WP-1", "WP Name": "Work 1", "Employee Name": "", "WP Quantity": 1},
        {"Domain": "Cloud Infra", "BP ID": "BP-2", "Project Name": "Proj A", "Product": "Prod", "Customer": "Cust", "WP Order ID": "WPO-2", "WP ID": "WP-2", "WP Name": "Work 2", "Employee Name": "", "WP Quantity": 1},
    ])
    (td / "router_sample.xlsx").unlink(missing_ok=True)
    df.to_excel(td / "router_sample.xlsx", index=False)

    # Offline dry-run
    run([
        "python", str(ROOT / "wpr_agent/scripts/router.py"),
        "--file", str(td / "router_sample.xlsx"),
        "--sheet", "Sheet1",
        "--registry", str(td / "registry.json"),
        "--offline", "--dry-run",
        "--artifact-dir", str(td / "art_offline"),
        "--report", str(td / "run_report_offline.json"),
        "--summary", str(td / "summary_offline.txt"),
    ])

    # Online stub success
    os.environ["ROUTER_JIRA_STUB"] = "1"
    os.environ["JIRA_STUB_SCENARIO"] = "success"
    run([
        "python", str(ROOT / "wpr_agent/scripts/router.py"),
        "--file", str(td / "router_sample.xlsx"),
        "--sheet", "Sheet1",
        "--registry", str(td / "registry.json"),
        "--online",
        "--artifact-dir", str(td / "art_stub_success"),
        "--report", str(td / "run_report_stub_success.json"),
        "--summary", str(td / "summary_stub_success.txt"),
    ])

    # Online stub rate-limit once
    os.environ["JIRA_STUB_SCENARIO"] = "rate_limit_once"
    run([
        "python", str(ROOT / "wpr_agent/scripts/router.py"),
        "--file", str(td / "router_sample.xlsx"),
        "--sheet", "Sheet1",
        "--registry", str(td / "registry.json"),
        "--online",
        "--artifact-dir", str(td / "art_stub_rl"),
        "--report", str(td / "run_report_stub_rl.json"),
        "--summary", str(td / "summary_stub_rl.txt"),
    ])

    # Checkpoint resume: skip first BP
    (td / "art_stub_success" / "router_checkpoint.json").write_text(json.dumps({"apply_progress": {"TEST": 1}}, indent=2), encoding="utf-8")
    os.environ["JIRA_STUB_SCENARIO"] = "success"
    run([
        "python", str(ROOT / "wpr_agent/scripts/router.py"),
        "--file", str(td / "router_sample.xlsx"),
        "--sheet", "Sheet1",
        "--registry", str(td / "registry.json"),
        "--online",
        "--artifact-dir", str(td / "art_stub_success"),
        "--report", str(td / "run_report_stub_resume.json"),
        "--summary", str(td / "summary_stub_resume.txt"),
    ])

    print("OK: stubbed scenarios completed. Inspect tmp_router artifacts for details.")


if __name__ == "__main__":
    main()

