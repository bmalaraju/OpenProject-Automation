from __future__ import annotations

"""
InfluxDB admin utility for WP Jira Agent state/input cleanup.

Actions
- --clear-issue-map [--project NM]: delete identity mappings (issue_map) in the bucket
- --clear-input: delete uploaded input rows (wpr_input) in the bucket
- --reupload --file work_packages.xlsx [--sheet Sheet1]: re-upload normalized Excel rows to wpr_input

Env required: INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

Example
  python wpr_agent/scripts/influx_admin.py --clear-issue-map --project NM \
      --reupload --file work_packages.xlsx --sheet MN
"""

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import load_dotenv


# Bootstrap env (root .env then wpr_agent/.env)
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_point(row: Dict[str, Any]):
    from influxdb_client import Point  # type: ignore

    bp_id = str(row.get("BP ID", "") or "")
    order_id = str(row.get("WP Order ID", "") or "")
    product = str(row.get("Product", "") or "")
    project_name = str(row.get("Project Name", "") or "")
    domain = str(row.get("Domain", "") or row.get("Domain1", "") or "")
    customer = str(row.get("Customer", "") or "")

    p = Point("wpr_input")
    p = p.tag("product", product)
    p = p.tag("order_id", order_id)
    p = p.tag("bp_id", bp_id)
    p = p.tag("project_name", project_name)
    p = p.tag("domain", domain)
    p = p.tag("customer", customer)
    for k, v in row.items():
        if k in ("Product", "WP Order ID", "BP ID", "Project Name", "Domain", "Domain1", "Customer"):
            continue
        if v is None:
            continue
        try:
            sval = str(v)
        except Exception:
            sval = ""
        p = p.field(k.replace(" ", "_"), sval)
    return p


def _delete_measurement(client: Any, bucket: str, org: str, measurement: str, project_key: str | None = None) -> None:
    del_api = client.delete_api()
    # Wide time window to cover all points; Influx requires a start/stop and a predicate
    start = "1970-01-01T00:00:00Z"
    stop = _now_iso()
    predicate = f'_measurement="{measurement}"'
    if project_key and measurement == "issue_map":
        predicate += f' AND project_key="{project_key}"'
    del_api.delete(start, stop, predicate, bucket=bucket, org=org)


def main() -> None:
    ap = argparse.ArgumentParser(description="InfluxDB admin: clear state/input and re-upload Excel")
    ap.add_argument("--clear-issue-map", action="store_true", help="Delete issue_map identity mappings")
    ap.add_argument("--project", help="Project key filter for issue_map (optional)")
    ap.add_argument("--clear-input", action="store_true", help="Delete wpr_input data")
    ap.add_argument("--reupload", action="store_true", help="Re-upload Excel to wpr_input after clearing")
    ap.add_argument("--file", "-f", help="Excel file path for reupload")
    ap.add_argument("--sheet", default="Sheet1", help="Excel sheet name (default Sheet1)")
    args = ap.parse_args()

    url = os.getenv("INFLUX_URL")
    token = os.getenv("INFLUX_TOKEN")
    org = os.getenv("INFLUX_ORG")
    bucket = os.getenv("INFLUX_BUCKET")
    if not (url and token and org and bucket):
        raise SystemExit("Missing INFLUX_URL/TOKEN/ORG/BUCKET in environment")

    try:
        import influxdb_client  # type: ignore
        from influxdb_client.client.write_api import SYNCHRONOUS  # type: ignore
    except Exception as ex:
        raise SystemExit(f"influxdb-client not installed: {ex}")

    client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)

    if args.clear_issue_map:
        _delete_measurement(client, bucket, org, "issue_map", project_key=(args.project or None))
        print(f"ok: cleared issue_map (project_key={args.project or '*'}).")

    if args.clear_input:
        _delete_measurement(client, bucket, org, "wpr_input")
        print("ok: cleared wpr_input.")

    if args.reupload:
        if not args.file:
            raise SystemExit("--reupload requires --file")
        # Load and normalize Excel, then write points
        df = pd.read_excel(args.file, sheet_name=args.sheet, engine="openpyxl").fillna("")
        # Defer import to avoid circulars
        from wpr_agent.tools.excel_tools import ensure_columns  # type: ignore

        df = ensure_columns(df)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        points: List[Any] = []
        for _, r in df.iterrows():
            row = {k: r.get(k, "") for k in df.columns}
            points.append(_to_point(row))
        if points:
            write_api.write(bucket=bucket, org=org, record=points)
        print(f"ok: uploaded {len(points)} rows to {bucket} (wpr_input)")


if __name__ == "__main__":
    main()

