import os
from influxdb_client import InfluxDBClient

def inspect_influx():
    url = os.getenv("INFLUX_URL")
    token = os.getenv("INFLUX_TOKEN")
    org = os.getenv("INFLUX_ORG")
    
    if not (url and token and org):
        print("Missing InfluxDB env vars.")
        return

    client = InfluxDBClient(url=url, token=token, org=org, timeout=10000)
    
    print(f"Connected to {url} (Org: {org})")
    
    # List Buckets
    print("\n--- Buckets ---")
    buckets_api = client.buckets_api()
    buckets = buckets_api.find_buckets().buckets
    for b in buckets:
        print(f"- {b.name} (ID: {b.id})")
        
        # List Measurements in this bucket
        if b.name in ["wpr-state", "wpr_state", "wpr_input"]:
            print(f"  Measurements in {b.name}:")
            query_api = client.query_api()
            flux = f'import "influxdata/influxdb/schema"\nschema.measurements(bucket: "{b.name}")'
            try:
                tables = query_api.query(flux)
                for table in tables:
                    for record in table.records:
                        m_name = record.get_value()
                        print(f"    - {m_name}")
                        
                        # Sample one record
                        if m_name == "wpr_input":
                            print(f"      [Sample Record for {m_name}]")
                            flux_sample = f'''from(bucket: "{b.name}") 
                                |> range(start: -1d) 
                                |> filter(fn: (r) => r["_measurement"] == "{m_name}") 
                                |> limit(n:1)'''
                            tables_sample = query_api.query(flux_sample)
                            for t in tables_sample:
                                for r in t.records:
                                    print(f"      Key: {r.get_field()} = {r.get_value()}")
                                    print(f"      Tags: {r.values.get('product')}, {r.values.get('order_id')}")
            except Exception as e:
                print(f"    Error listing measurements: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    inspect_influx()
