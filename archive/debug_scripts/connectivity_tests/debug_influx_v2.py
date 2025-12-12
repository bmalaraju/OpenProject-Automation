import os
import sys
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))
load_dotenv()

url = os.getenv("INFLUX_URL")
token = os.getenv("INFLUX_TOKEN")
org = os.getenv("INFLUX_ORG")
bucket = os.getenv("INFLUX_BUCKET")

print(f"Connecting to {url}, org={org}, bucket={bucket}")

client = InfluxDBClient(url=url, token=token, org=org)

def test_write():
    print("Testing Write...")
    try:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        p = Point("test_measurement").tag("location", "debug").field("value", 1.0)
        write_api.write(bucket=bucket, org=org, record=p)
        print("Write Success!")
    except Exception as e:
        print(f"Write Failed: {e}")

def test_flux_query():
    print("Testing Flux Query...")
    try:
        query_api = client.query_api()
        query = f'from(bucket: "{bucket}") |> range(start: -1h) |> filter(fn: (r) => r["_measurement"] == "test_measurement")'
        tables = query_api.query(query, org=org)
        print(f"Flux Query Success! Rows: {len(tables)}")
    except Exception as e:
        print(f"Flux Query Failed: {e}")

def test_influxql_query():
    print("Testing InfluxQL Query (v1 compatibility)...")
    # InfluxDB 3 supports InfluxQL via /query endpoint usually?
    # Or via v2 client if configured?
    # v2 client doesn't have native InfluxQL support except via raw request or specific helper?
    # Let's try raw request using the client's session
    try:
        # Construct InfluxQL query
        # endpoint: /query?db=bucket&q=SELECT...
        # Note: InfluxDB 3 maps 'database' to 'bucket' usually
        import requests
        headers = {"Authorization": f"Token {token}"}
        q = f"SELECT * FROM test_measurement WHERE time > now() - 1h"
        params = {"db": bucket, "q": q}
        # Try /query endpoint (v1)
        r = requests.get(f"{url}/query", headers=headers, params=params)
        if r.status_code == 200:
            print(f"InfluxQL Success! {r.json()}")
        else:
            print(f"InfluxQL Failed: {r.status_code} {r.text}")
    except Exception as e:
        print(f"InfluxQL Request Failed: {e}")

if __name__ == "__main__":
    test_write()
    test_flux_query()
    test_influxql_query()
