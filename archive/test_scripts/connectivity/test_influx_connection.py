
import os
from influxdb_client import InfluxDBClient
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("INFLUX_URL")
token = os.getenv("INFLUX_TOKEN")
org = "" # Try empty org for InfluxDB 3
bucket = "wpr-state"

print(f"Connecting to {url} with org={org}, bucket={bucket}")
print(f"Token: {token[:5]}...{token[-5:]}")

try:
    client = InfluxDBClient(url=url, token=token, org=org)
    print("Client initialized.")
    
    print("Checking health...")
    health = client.health()
    print(f"Health: {health}")

    print("Testing Flux Query...")
    query_api = client.query_api()
    flux = f'from(bucket: "{bucket}") |> range(start: -1h) |> limit(n:1)'
    try:
        tables = query_api.query(flux)
        print(f"Flux Query Successful. Tables: {len(tables)}")
    except Exception as e:
        print(f"Flux Query Failed: {e}")

    # print("Listing buckets...")
    # buckets_api = client.buckets_api()
    # buckets = buckets_api.find_buckets()
    # print(f"Buckets found: {len(buckets.buckets)}")
    # for b in buckets.buckets:
    #     print(f" - {b.name}")
    write_api = client.write_api()
    from influxdb_client import Point
    p = Point("test_measurement").tag("location", "test").field("value", 1.0)
    write_api.write(bucket=bucket, org=org, record=p)
    print("Write successful.")

except Exception as e:
    print(f"Error: {e}")
