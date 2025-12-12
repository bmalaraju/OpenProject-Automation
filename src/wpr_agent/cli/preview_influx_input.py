from __future__ import annotations

"""
Preview Influx input snapshot for router: counts by product and order.

Usage:
  python wpr_agent/scripts/preview_influx_input.py --since 30d
  python wpr_agent/scripts/preview_influx_input.py --batch-id 20251104153000
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Bootstrap env and paths like other scripts
BASE_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(ROOT / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

from wpr_agent.router.tools.influx_source import read_influx_df_tool, group_product_order_from_df_tool  # type: ignore


def main() -> None:
    ap = argparse.ArgumentParser(description="Preview Influx input rows for router grouping")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--since", help="Range window (e.g., 30d, 12h)")
    src.add_argument("--batch-id", help="Specific ingestion batch_id")
    args = ap.parse_args()

    df = read_influx_df_tool(since=args.since if not args.batch_id else None, batch_id=args.batch_id)
    if df is None or len(df) == 0:
        print("empty: no rows returned from Influx (check --since/--batch-id and ingestion)")
        # Deep-dive: list latest batch_ids and counts
        try:
            import os
            import influxdb_client  # type: ignore
            url, token, org, bucket = os.getenv("INFLUX_URL"), os.getenv("INFLUX_TOKEN"), os.getenv("INFLUX_ORG"), os.getenv("INFLUX_BUCKET")
            client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
            q = client.query_api()
            # last 10 ingestion_run entries
            flux = f'''from(bucket: "{bucket}")
  |> range(start: -7d)
  |> filter(fn: (r) => r["_measurement"] == "ingestion_run")
  |> keep(columns: ["_time","batch_id","_field","_value"]) 
  |> sort(columns:["_time"], desc:true) 
  |> limit(n: 50)'''
            tables = q.query(flux)
            seen = []
            for t in tables or []:
                for rec in t.records or []:
                    bid = str(rec.values.get("batch_id") or "")
                    if bid and bid not in seen:
                        seen.append(bid)
            if seen:
                print("recent batch_ids:", ", ".join(seen[:10]))
                # check counts for first batch
                bid = seen[0]
                flux2 = f'''from(bucket: "{bucket}")
  |> range(start: -7d)
  |> filter(fn: (r) => r["_measurement"] == "wpr_input")
  |> filter(fn: (r) => r["batch_id"] == "{bid}")
  |> count()'''
                tables2 = q.query(flux2)
                total = 0
                for t2 in tables2 or []:
                    for rec2 in t2.records or []:
                        try:
                            total += int(rec2.get_value() or 0)
                        except Exception:
                            pass
                print(f"wpr_input count for batch_id={bid}: {total}")
        except Exception as ex:
            print(f"debug_error: {ex}")
        return
    print(f"rows: {len(df)} cols: {len(df.columns)}")
    # Show sample columns
    print("columns:", ", ".join(list(df.columns)[:12]))
    # Group products and orders
    grouped = group_product_order_from_df_tool(df)
    print(f"products: {len(grouped)}")
    total_orders = 0
    for prod, orders in grouped:
        total_orders += len(orders)
    print(f"orders: {total_orders}")
    # Print a small sample
    for prod, orders in grouped[:5]:
        print(f"- product='{prod}' orders={len(orders)} sample_order_ids={[oid for oid,_ in orders[:3]]}")


if __name__ == "__main__":
    main()
