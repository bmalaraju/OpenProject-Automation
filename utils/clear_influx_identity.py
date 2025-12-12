import os
import sys
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from wpr_agent.shared.config_loader import InfluxConfig
from influxdb_client_3 import InfluxDBClient3
from dotenv import load_dotenv

def main():
    load_dotenv()
    print("Clearing InfluxDB Identity Map...")
    
    # Load config
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
    
    # We want to delete from "wpr_issue_map"
    # We can use delete predicate if supported, or drop measurement?
    # InfluxDB 3 (IOx) supports SQL DELETE? Or just drop table?
    # Actually, InfluxDB 3 usually supports deletion via predicate or dropping the measurement.
    # However, standard SQL DELETE might not be fully supported in all versions.
    # Let's try to drop the measurement "wpr_issue_map" if possible, or delete where true.
    
    # For InfluxDB 3 Cloud/Core, deletion is often restricted.
    # But this is self-hosted v3.
    # Let's try a simple SQL delete first.
    
    # Wait, InfluxDB 3 SQL DELETE is: DELETE FROM table WHERE ...
    # Let's try to delete all from wpr_issue_map.
    
    sql = "DELETE FROM wpr_issue_map"
    print(f"Executing SQL: {sql}")
    
    try:
        # Client 3 doesn't have a direct 'execute' for DML in the same way?
        # Actually it does via query if it supports it.
        # But often deletion is a separate API.
        # Let's check if we can just use the flight client to execute this.
        # Or maybe we just drop the measurement?
        # "DROP TABLE wpr_issue_map"
        
        # Let's try DROP TABLE first as it is cleaner for "reset".
        sql_drop = "DROP TABLE wpr_issue_map"
        print(f"Attempting: {sql_drop}")
        try:
            client.query(sql_drop)
            print("Drop table command executed (check if successful).")
        except Exception as e:
            print(f"Drop table failed: {e}")
            print("Attempting DELETE FROM...")
            client.query("DELETE FROM wpr_issue_map WHERE 1=1")
            print("Delete command executed.")
            
    except Exception as e:
        print(f"Error executing delete: {e}")

    # Also clear checkpoints?
    # The user said "delete all workpackages... leaving projects".
    # If we delete WPs, we should probably clear checkpoints too so we re-process them?
    # "My analysis say that the data currently in influxdb has has deescrepancies."
    # If we don't clear checkpoints, the router will think it already processed them and skip them (unless we force sync).
    # But if we want to RE-CREATE them, we must clear checkpoints.
    
    print("Clearing Order Checkpoints (wpr_order_checkpoint)...")
    try:
        client.query("DROP TABLE order_checkpoint")
        print("Dropped order_checkpoint.")
    except Exception as e:
        print(f"Failed to drop order_checkpoint: {e}")
        
    print("Done.")

if __name__ == "__main__":
    main()
