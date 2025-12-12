
import os
from influxdb_client_3 import InfluxDBClient3
from dotenv import load_dotenv

load_dotenv()

# Hardcoded for verification based on user input
host = "http://212.2.245.85:8181"
token = "apiv3_cMe54DIsXtHFfMBNAAGBM_-6djfLM6aqDwnJUrtuc56Kkk_8QeHyusU0B-34CqW3FxMz5-iey-aH7WZIoFAu2w"
org = ""
database = "wpr-state"

print(f"Connecting to {host} with database={database}")

try:
    client = InfluxDBClient3(
        host=host,
        token=token,
        org=org,
        database=database,
        auth_scheme="Bearer"
    )
    print("Client initialized.")
    
    # Test Write
    print("Writing test point...")
    client.write(
        database=database, 
        record=[{"measurement": "test_measurement", "tags": {"location": "test_v3"}, "fields": {"value": 1.0}}],
        write_precision="s"
    )
    print("Write successful.")

    # Test Query (SQL)
    print("Querying router_run...")
    query = "SELECT * FROM router_run ORDER BY time DESC LIMIT 5"
    table = client.query(query=query, language="sql")
    print(f"Query successful. Rows: {table.num_rows}")
    print(table.to_pylist())

except Exception as e:
    print(f"Error: {e}")
