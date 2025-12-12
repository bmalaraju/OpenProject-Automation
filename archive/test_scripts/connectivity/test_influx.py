import os
from dotenv import load_dotenv
load_dotenv()

try:
    from wpr_agent.state.influx_store import InfluxStore
    print("Initializing InfluxStore...")
    store = InfluxStore()
    print(f"InfluxStore URL: {store.url}")
    print("Testing query...")
    # Simple query to check connectivity
    flux = f'from(bucket: "{store.bucket}") |> range(start: -1m) |> limit(n:1)'
    store.query_api.query(flux)
    print("InfluxStore query successful.")
except Exception as e:
    print(f"InfluxStore test failed: {e}")
    import traceback
    traceback.print_exc()
