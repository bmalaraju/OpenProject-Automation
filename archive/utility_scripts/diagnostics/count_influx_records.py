import os
import sys
import json
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from wpr_agent.shared.config_loader import InfluxConfig
from influxdb_client_3 import InfluxDBClient3
from dotenv import load_dotenv

def main():
    load_dotenv()
    batch_id = "20251201211608"
    registry_path = "config/product_project_registry.json"
    
    print(f"Counting records for batch_id={batch_id} filtered by {registry_path}")
    
    # Load registry
    try:
        with open(registry_path, "r") as f:
            reg_data = json.load(f)
            # Handle both direct dict and "registry" key format
            registry = reg_data.get("registry", reg_data)
            products = list(registry.keys())
            print(f"Found {len(products)} products in registry: {products}")
    except Exception as e:
        print(f"Error loading registry: {e}")
        return

    # Load Influx config
    try:
        cfg = InfluxConfig.load()
    except Exception as e:
        print(f"Error loading Influx config: {e}")
        return

    client = InfluxDBClient3(
        host=cfg.url,
        token=cfg.token,
        org=cfg.org,
        database=cfg.bucket
    )
    
    # Construct SQL query
    # We need to filter by product. In SQL: product IN ('p1', 'p2', ...)
    # Note: InfluxDB 3 SQL uses single quotes for strings.
    
    if not products:
        print("Registry is empty. Count is 0.")
        return

    product_list_str = ", ".join([f"'{p}'" for p in products])
    
    query = f"""
    SELECT COUNT(*) as count
    FROM "wpr_input" 
    WHERE batch_id = '{batch_id}'
    AND product IN ({product_list_str})
    """
    
    print(f"Executing SQL: {query}")
    
    try:
        table = client.query(query=query, language="sql")
        df = table.to_pandas()
        if not df.empty:
            count = df.iloc[0]['count']
            print(f"\nTotal Records: {count}")
        else:
            print("\nTotal Records: 0")
            
    except Exception as e:
        print(f"Query failed: {e}")

if __name__ == "__main__":
    main()
