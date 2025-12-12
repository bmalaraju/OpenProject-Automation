import os
import sys
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from wpr_agent.shared.config_loader import InfluxConfig
from influxdb_client_3 import InfluxDBClient3
from dotenv import load_dotenv

def main():
    load_dotenv()
    filename = "11.20.WP Orders_20-11-2025_v01.xlsx"
    print(f"Searching for batch_id for file: {filename}")
    
    try:
        cfg = InfluxConfig.load()
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    client = InfluxDBClient3(
        host=cfg.url,
        token=cfg.token,
        org=cfg.org,
        database=cfg.bucket
    )
    
    # Query for the file
    # We look for distinct batch_id where source_filename matches
    query = f"""
    SELECT DISTINCT batch_id, source_filename, time 
    FROM "wpr_input" 
    WHERE source_filename = '{filename}'
    ORDER BY time DESC
    LIMIT 5
    """
    
    print(f"Executing SQL: {query}")
    
    try:
        table = client.query(query=query, language="sql")
        df = table.to_pandas()
        if df.empty:
            print("No batch found for this file.")
        else:
            print("\nFound Batches:")
            print(df)
            # Print the latest batch ID for easy copy-paste
            latest = df.iloc[0]['batch_id']
            print(f"\nLatest Batch ID: {latest}")
            
    except Exception as e:
        print(f"Query failed: {e}")

if __name__ == "__main__":
    main()
