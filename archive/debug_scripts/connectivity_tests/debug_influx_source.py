import os
import sys
import pandas as pd
# Ensure src is in path
sys.path.insert(0, os.path.abspath("src"))

from dotenv import load_dotenv
load_dotenv()

from wpr_agent.router.tools.influx_source import read_influx_df_tool

def main():
    batch_id = "20251201211608"
    print(f"Testing read_influx_df_tool with batch_id={batch_id}")
    
    # Enable debug logging in the tool
    os.environ["INFLUX_DEBUG"] = "1"
    
    try:
        df = read_influx_df_tool(batch_id=batch_id)
        print(f"Result DataFrame shape: {df.shape}")
        if not df.empty:
            print(df.head())
        else:
            print("DataFrame is empty.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
