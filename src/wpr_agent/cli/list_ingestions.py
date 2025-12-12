from __future__ import annotations

"""
List recent ingestion runs and their input row counts per batch_id.

Usage:
  python wpr_agent/scripts/list_ingestions.py --since 30d --limit 10

This script bootstraps environment from .env files like other wpr_agent scripts.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Bootstrap env and paths (match other scripts)
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="List recent ingestion_run entries and input row counts")
    ap.add_argument("--since", default="30d", help="Time window for ingestion_run (default 30d)")
    ap.add_argument("--limit", type=int, default=10, help="Max number of runs to list (default 10)")
    args = ap.parse_args()

    url = os.getenv("INFLUX_URL")
    token = os.getenv("INFLUX_TOKEN")
    org = os.getenv("INFLUX_ORG")
    bucket = os.getenv("INFLUX_BUCKET")
    if not (url and token and org and bucket):
        raise SystemExit("Missing INFLUX_URL/TOKEN/ORG/BUCKET in environment (ensure .env is loaded)")

    try:
        import influxdb_client  # type: ignore
    except Exception as ex:
        raise SystemExit(f"influxdb-client not installed: {ex}")

    client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
    q = client.query_api()

    flux = f'''from(bucket: "{bucket}")
  |> range(start: -{args.since})
  |> filter(fn: (r) => r["_measurement"] == "ingestion_run")
  |> keep(columns: ["_time","_field","_value","batch_id"])
  |> sort(columns:["_time"], desc:true)'''
    tables = q.query(flux)

    # Group fields by batch_id; collect most recent time per batch
    runs: Dict[str, Dict[str, Any]] = {}
    for table in tables or []:
        for rec in table.records or []:
            try:
                bid = str(rec.values.get("batch_id") or "")
                if not bid:
                    continue
                r = runs.setdefault(bid, {"time": rec.get_time(), "fields": {}})
                # Keep newest timestamp
                if rec.get_time() and (r["time"] is None or rec.get_time() > r["time"]):
                    r["time"] = rec.get_time()
                r["fields"][str(rec.get_field())] = rec.get_value()
            except Exception:
                continue

    # Limit to N most recent by time
    items = sorted(runs.items(), key=lambda kv: (kv[1]["time"] or 0), reverse=True)[: int(args.limit)]

    # For each, count wpr_input rows for the batch
    results: List[Dict[str, Any]] = []
    for bid, meta in items:
        flux_rows = f'''from(bucket: "{bucket}")
  |> range(start: -90d)
  |> filter(fn: (r) => r["_measurement"] == "wpr_input")
  |> filter(fn: (r) => r["batch_id"] == "{bid}")
  |> keep(columns:["_time","_field"])
  |> group()
  |> count()'''
        count = 0
        try:
            tables_rows = q.query(flux_rows)
            for t in tables_rows or []:
                for rec in t.records or []:
                    # Any count from pivoted records; conservative sum
                    try:
                        count += int(rec.get_value() or 0)
                    except Exception:
                        continue
        except Exception:
            count = 0
        results.append({
            "batch_id": bid,
            "time": str(meta.get("time")),
            "rows_count": count,
            "file_hash": meta.get("fields", {}).get("file_hash"),
            "source_filename": meta.get("fields", {}).get("source_filename"),
            "rows_recorded": meta.get("fields", {}).get("rows"),
        })

    import json
    print(json.dumps({"runs": results}, indent=2))


if __name__ == "__main__":
    main()
