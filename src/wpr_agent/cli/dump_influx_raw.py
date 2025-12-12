from __future__ import annotations

"""
Dump a small sample of raw records from Influx measurement 'wpr_input' to diagnose query visibility.

Usage:
  python wpr_agent/scripts/dump_influx_raw.py --since 30m [--batch-id BID] [--limit 10]
"""

import argparse
import os

from dotenv import load_dotenv


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump raw Influx wpr_input sample")
    ap.add_argument("--since", default="30m")
    ap.add_argument("--batch-id")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    load_dotenv(".env", override=False)
    load_dotenv("wpr_agent/.env", override=False)

    url, token, org, bucket = os.getenv("INFLUX_URL"), os.getenv("INFLUX_TOKEN"), os.getenv("INFLUX_ORG"), os.getenv("INFLUX_BUCKET")
    if not (url and token and org and bucket):
        print("env_error: missing INFLUX_* (ensure .env is loaded)")
        return
    try:
        import influxdb_client  # type: ignore
    except Exception as ex:
        print(f"client_error: {ex}")
        return
    client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
    q = client.query_api()
    rng = args.since
    if rng and rng[0].isdigit():
        rng = f"-{rng}"
    bid_filter = f'\n  |> filter(fn: (r) => r["batch_id"] == "{args.batch_id}")' if args.batch_id else ""
    flux = f'''from(bucket: "{bucket}")
  |> range(start: {rng})
  |> filter(fn: (r) => r["_measurement"] == "wpr_input"){bid_filter}
  |> limit(n: {int(args.limit)})'''
    print("flux:\n" + flux)
    try:
        tables = q.query(flux)
    except Exception as ex:
        print(f"query_error: {ex}")
        return
    total = 0
    for t in tables or []:
        for rec in t.records or []:
            total += 1
            print({k: v for k, v in rec.values.items() if k not in ("_start","_stop")})
    print(f"records: {total}")


if __name__ == "__main__":
    main()

