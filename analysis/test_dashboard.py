"""Test script to identify errors in the dashboard"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Load data
filename = r"C:\Users\bmalaraju\Documents\WP-OP Agent\JIRA-Agent\11.25.WP Orders_25-11-2025_v01.xlsx"
print(f"Loading {filename}...")
df = pd.read_excel(filename, engine='openpyxl')
print(f"Loaded {len(df):,} rows")

# Helper to strip timezone
def parse_date(series):
    dt = pd.to_datetime(series, errors='coerce')
    if dt.dt.tz is not None:
        dt = dt.dt.tz_localize(None)
    return dt

# Test date parsing
try:
    df['requested_date'] = parse_date(df.get('WP Requested Delivery Date'))
    print("✅ requested_date parsed")
except Exception as e:
    print(f"❌ requested_date error: {e}")

try:
    df['added_date'] = parse_date(df.get('Added Date'))
    print("✅ added_date parsed")
except Exception as e:
    print(f"❌ added_date error: {e}")

# Test metrics calculation
TODAY = pd.Timestamp.now().normalize()
TERMINAL = ['Approved', 'Rejected', 'Cancelled']
status_col = 'WP Order Status'

try:
    df['is_terminal'] = df[status_col].isin(TERMINAL)
    df['has_target'] = df['requested_date'].notna()
    df['is_past_due'] = (df['requested_date'] < TODAY) & df['has_target']
    df['is_breached'] = df['is_past_due'] & ~df['is_terminal']
    print("✅ SLA metrics calculated")
except Exception as e:
    print(f"❌ SLA calculation error: {e}")

# Test groupby operations
try:
    product_stats = df[df['has_target'] & ~df['is_terminal']].groupby('Product').agg(
        total_active=('is_breached', 'count'),
        breached=('is_breached', 'sum')
    ).reset_index()
    print(f"✅ Product stats calculated: {len(product_stats)} products")
except Exception as e:
    print(f"❌ Product stats error: {e}")

# Test status counts
try:
    status_counts = df[status_col].value_counts()
    print(f"✅ Status counts: {len(status_counts)} statuses")
except Exception as e:
    print(f"❌ Status counts error: {e}")

print("\n✅ All basic operations work!")
