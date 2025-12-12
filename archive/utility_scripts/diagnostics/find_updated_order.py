import sys
from dotenv import load_dotenv
load_dotenv()
from wpr_agent.shared import influx_helpers

batch_id = "backfill-test-1"

print(f"Querying batch {batch_id}...")
df = influx_helpers.query_wpr_rows(batch_id=batch_id)
if df is None or df.empty:
    print("No rows found.")
    sys.exit(1)

print("Columns:", df.columns.tolist())

# Find rows where "Updated Date" is not empty/null
if "Updated Date" in df.columns:
    subset = df[df["Updated Date"].notna() & (df["Updated Date"] != "")]
    if not subset.empty:
        print(f"Found {len(subset)} rows with Updated Date.")
        # Pick the first one
        row = subset.iloc[0]
        order_id = row["WP Order ID"]
        updated_date = row["Updated Date"]
        print(f"Selected Order ID: {order_id}")
        print(f"Updated Date Value: {updated_date}")
    else:
        print("No rows with Updated Date found.")
else:
    print("'Updated Date' column not found in DataFrame.")
