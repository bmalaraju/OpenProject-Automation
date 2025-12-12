import os
import sys
from datetime import datetime
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from wpr_agent.shared.config_loader import InfluxConfig
from influxdb_client import InfluxDBClient
from dotenv import load_dotenv

def main():
    load_dotenv()
    print("Clearing InfluxDB Identity Map (v2 API)...")
    
    # Load config
    try:
        cfg = InfluxConfig.load()
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # Initialize v2 client
    client = InfluxDBClient(
        url=cfg.url,
        token=cfg.token,
        org=cfg.org
    )
    
    delete_api = client.delete_api()
    
    # Delete from 1970 to 2100
    start = "1970-01-01T00:00:00Z"
    stop = "2100-01-01T00:00:00Z"
    
    bucket = cfg.bucket
    
    print(f"Deleting from bucket: {bucket}")
    
    # Delete wpr_issue_map
    print("Deleting measurement: wpr_issue_map")
    try:
        delete_api.delete(start, stop, '_measurement="wpr_issue_map"', bucket=bucket, org=cfg.org)
        print("  Success.")
    except Exception as e:
        print(f"  Failed: {e}")

    # Delete order_checkpoint
    print("Deleting measurement: order_checkpoint")
    try:
        delete_api.delete(start, stop, '_measurement="order_checkpoint"', bucket=bucket, org=cfg.org)
        print("  Success.")
    except Exception as e:
        print(f"  Failed: {e}")
        
    # Delete wpr_src_fp (source fingerprints)
    print("Deleting measurement: wpr_src_fp")
    try:
        delete_api.delete(start, stop, '_measurement="wpr_src_fp"', bucket=bucket, org=cfg.org)
        print("  Success.")
    except Exception as e:
        print(f"  Failed: {e}")

    print("Done.")

if __name__ == "__main__":
    main()
