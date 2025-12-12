import os
from influxdb_client import InfluxDBClient
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("INFLUX_URL")
token = os.getenv("INFLUX_TOKEN")
org = os.getenv("INFLUX_ORG")
bucket = os.getenv("INFLUX_BUCKET") or "wpr-state"

print(f"Connecting to {url}, Bucket: {bucket}")

client = InfluxDBClient(url=url, token=token, org=org, timeout=10000)
query_api = client.query_api()

# Query 1 record
flux = f'''from(bucket: "{bucket}")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "wpr_input")
  |> limit(n:1)'''

print("Querying 1 record from wpr_input...")
try:
    tables = query_api.query(flux)
    found = False
    for table in tables:
        for record in table.records:
            found = True
            print(f"\n[Record Found]")
            print(f"Measurement: {record.get_measurement()}")
            print(f"Field: {record.get_field()} = {record.get_value()}")
            print("Tags:")
            for k, v in record.values.items():
                if k not in ["_value", "_time", "_start", "_stop", "_field", "_measurement", "result", "table"]:
                    print(f"  - {k}: {v}")
            break
        if found: break
    
    if not found:
        print("No records found in wpr_input.")

except Exception as e:
    print(f"Error: {e}")
