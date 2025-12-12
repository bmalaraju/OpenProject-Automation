
import os
import sys
from pathlib import Path
import pandas as pd

# Bootstrap env and paths
BASE_DIR = Path(__file__).resolve().parents[0]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
from dotenv import load_dotenv
load_dotenv()

from wpr_agent.router.tools.influx_source import read_influx_df_tool

def debug_data():
    batch_id = "20251202172311" # From the last run
    print(f"Reading data for batch_id: {batch_id}")
    
    df = read_influx_df_tool(batch_id=batch_id)
    
    print(f"Columns: {list(df.columns)}")
    
    # Check for STD column
    status_col = None
    for c in df.columns:
        if "std" in c.lower():
            print(f"Found std-like column: '{c}'")
            if c.lower().strip() == "std":
                status_col = c
    
    if status_col:
        print(f"Using std column: '{status_col}'")
        # Check specific failing order
        failing_order = "WPO00187674"
        row = df[df["WP Order ID"] == failing_order]
        if not row.empty:
            print(f"Row for {failing_order}:")
            print(row[[status_col, "WP Order ID", "Product"]].to_string())
            val = row.iloc[0][status_col]
            print(f"Value type: {type(val)}")
            print(f"Value repr: {repr(val)}")
        else:
            print(f"Order {failing_order} not found in DF")
            
        # Check how many are empty
        empty_count = df[df[status_col].isna() | (df[status_col] == "")].shape[0]
        print(f"Total rows: {len(df)}")
        print(f"Empty std rows: {empty_count}")
    else:
        print("CRITICAL: 'STD' column not found!")

if __name__ == "__main__":
    debug_data()
