import pandas as pd
import os

# Source file
source_file = "11.25.WP Orders_25-11-2025_v01.xlsx"

if not os.path.exists(source_file):
    print(f"Source file {source_file} not found!")
    exit(1)

print(f"Reading {source_file}...")
# Read the file
df = pd.read_excel(source_file, sheet_name="WP_Overall_Order_Report")

# Take top 5 rows
sample_df = df.head(5)

# Save as test_trigger.xlsx
output_file = "automation/test_trigger.xlsx"
sample_df.to_excel(output_file, sheet_name="WP_Overall_Order_Report", index=False)

print(f"Created {output_file} with {len(sample_df)} rows from real data.")
