import sys
from dotenv import load_dotenv
load_dotenv()
from wpr_agent.shared import influx_helpers

batch_id = "backfill-test-1"
order_id = "WPO00098660"

print(f"Querying batch {batch_id} for order {order_id}...")
df = influx_helpers.query_wpr_rows(batch_id=batch_id)
if df is None or df.empty:
    print("No rows found.")
    sys.exit(1)

subset = df[df["WP Order ID"] == order_id]
if subset.empty:
    print(f"Order {order_id} not found.")
    sys.exit(1)

print("WP Order Status values:")
print(subset["WP Order Status"].unique())
