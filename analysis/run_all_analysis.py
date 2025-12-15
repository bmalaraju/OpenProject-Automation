"""
WP Orders Analytics - Comprehensive Report Runner
Runs all analysis notebooks with the specified Excel file.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Configuration
EXCEL_FILE = r'c:\Users\bmalaraju\Documents\WP-OP Agent\JIRA-Agent\11.25.WP Orders_25-11-2025_v01.xlsx'
TODAY = pd.Timestamp.now().normalize()
TERMINAL_STATUSES = ['Approved', 'Cancelled', 'Rejected']

print("=" * 80)
print("📊 WP ORDERS COMPREHENSIVE ANALYTICS REPORT")
print(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 80)

# Load data
print("\n📁 Loading data...")
df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
print(f"   ✅ Loaded {len(df):,} rows, {len(df.columns)} columns")

# Helper to strip timezone from dates
def strip_tz(series):
    s = pd.to_datetime(series, errors='coerce')
    if s.dt.tz is not None:
        s = s.dt.tz_localize(None)
    return s

# Parse dates
df['requested_date'] = strip_tz(df.get('WP Requested Delivery Date'))
df['added_date'] = strip_tz(df.get('Added Date'))
df['approved_date'] = strip_tz(df.get('Approved Date'))
df['acknowledged_date'] = strip_tz(df.get('Acknowledgement Date'))
df['submitted_date'] = strip_tz(df.get('Submitted Date'))

# Parse quantities
df['quantity'] = pd.to_numeric(df.get('WP Quantity'), errors='coerce').fillna(0)
df['completed'] = pd.to_numeric(df.get('WP Completed Qty'), errors='coerce').fillna(0)

# Status flags
status_col = 'WP Order Status'
df['is_terminal'] = df[status_col].isin(TERMINAL_STATUSES)
df['is_approved'] = df[status_col] == 'Approved'
df['is_rejected'] = df[status_col] == 'Rejected'
df['is_cancelled'] = df[status_col] == 'Cancelled'
df['is_objected'] = df[status_col] == 'Objected'

# SLA flags
df['has_target'] = df['requested_date'].notna()
df['is_past_due'] = (df['requested_date'] < TODAY) & df['has_target']
df['is_breached'] = df['is_past_due'] & ~df['is_terminal']
df['days_overdue'] = np.where(df['is_past_due'], (TODAY - df['requested_date']).dt.days, 0)
df['is_at_risk'] = (
    (df['requested_date'] >= TODAY) & 
    (df['requested_date'] <= TODAY + timedelta(days=7)) &
    ~df['is_terminal'] & df['has_target']
)

# ITD
if 'In-Time Delivery' in df.columns:
    df['itd_clean'] = df['In-Time Delivery'].fillna('').astype(str).str.lower().str.strip()
    df['is_on_time'] = df['itd_clean'].isin(['yes', 'y', '1', 'true'])
    df['itd_known'] = df['itd_clean'].isin(['yes', 'y', '1', 'true', 'no', 'n', '0', 'false'])
else:
    df['itd_known'] = False
    df['is_on_time'] = False

# Cycle times
df['time_to_ack'] = (df['acknowledged_date'] - df['added_date']).dt.days
df['time_to_approve'] = (df['approved_date'] - df['submitted_date']).dt.days
df['total_cycle'] = (df['approved_date'] - df['added_date']).dt.days

# ============================================================================
# NOTEBOOK 1: SLA ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("📊 NOTEBOOK 1: SLA ANALYSIS")
print("=" * 80)

total_orders = len(df)
orders_with_date = df['has_target'].sum()
active_orders = (~df['is_terminal'] & df['has_target']).sum()
breached_orders = df['is_breached'].sum()
at_risk_orders = df['is_at_risk'].sum()
compliant_active = active_orders - breached_orders - at_risk_orders

breach_pct = (breached_orders / active_orders * 100) if active_orders > 0 else 0
at_risk_pct = (at_risk_orders / active_orders * 100) if active_orders > 0 else 0
compliant_pct = 100 - breach_pct - at_risk_pct

print(f"\n📋 Total Orders:           {total_orders:,}")
print(f"📅 With Target Date:        {orders_with_date:,}")
print(f"🔄 Active (Non-Terminal):   {active_orders:,}")
print(f"\n🚨 BREACHED (Past SLA):     {breached_orders:,} ({breach_pct:.1f}%)")
print(f"⚠️  AT RISK (Due ≤7 days):  {at_risk_orders:,} ({at_risk_pct:.1f}%)")
print(f"✅ COMPLIANT:               {compliant_active:,} ({compliant_pct:.1f}%)")

# Breach by product
print(f"\n--- SLA Breach % by Product (Top 10) ---")
product_stats = df[df['has_target'] & ~df['is_terminal']].groupby('Product').agg(
    total_active=('is_breached', 'count'),
    breached=('is_breached', 'sum')
).reset_index()
product_stats['breach_pct'] = (product_stats['breached'] / product_stats['total_active'] * 100).round(1)
product_stats = product_stats.sort_values('breach_pct', ascending=False)
for _, row in product_stats.head(10).iterrows():
    print(f"   {row['Product'][:40]:<40} {row['breach_pct']:>6.1f}% ({row['breached']:.0f}/{row['total_active']:.0f})")

# Most overdue
print(f"\n--- Top 10 Most Overdue Orders ---")
overdue = df[df['is_breached'] & (df['days_overdue'] > 0)].nlargest(10, 'days_overdue')
for _, row in overdue.iterrows():
    print(f"   {row['WP Order ID']:<20} {row['days_overdue']:>5.0f} days  ({row['Product'][:30]})")

# ============================================================================
# NOTEBOOK 2: ORDER STATUS METRICS
# ============================================================================
print("\n" + "=" * 80)
print("📊 NOTEBOOK 2: ORDER STATUS METRICS")
print("=" * 80)

approved = df['is_approved'].sum()
rejected = df['is_rejected'].sum()
cancelled = df['is_cancelled'].sum()
objected = df['is_objected'].sum()
terminal = df['is_terminal'].sum()
in_progress = total_orders - terminal

total_qty = df['quantity'].sum()
completed_qty = df['completed'].sum()
completion_rate = (completed_qty / total_qty * 100) if total_qty > 0 else 0

non_cancelled = total_orders - cancelled
approval_rate = (approved / non_cancelled * 100) if non_cancelled > 0 else 0

submitted_base = approved + rejected + objected
rejection_rate = (rejected / submitted_base * 100) if submitted_base > 0 else 0
objection_rate = (objected / submitted_base * 100) if submitted_base > 0 else 0

print(f"\n📋 Total Orders:        {total_orders:,}")
print(f"\n🔄 STATUS BREAKDOWN:")
print(f"   ✅ Approved:         {approved:,} ({approved/total_orders*100:.1f}%)")
print(f"   ❌ Rejected:         {rejected:,} ({rejected/total_orders*100:.1f}%)")
print(f"   🚫 Cancelled:        {cancelled:,} ({cancelled/total_orders*100:.1f}%)")
print(f"   ⚠️ Objected:         {objected:,} ({objected/total_orders*100:.1f}%)")
print(f"   🔄 In Progress:      {in_progress:,} ({in_progress/total_orders*100:.1f}%)")
print(f"\n📈 KEY RATES:")
print(f"   Approval Rate:       {approval_rate:.1f}%")
print(f"   Rejection Rate:      {rejection_rate:.1f}%")
print(f"   Objection Rate:      {objection_rate:.1f}%")
print(f"\n📦 QUANTITY METRICS:")
print(f"   Total Quantity:      {total_qty:,.0f}")
print(f"   Completed Quantity:  {completed_qty:,.0f}")
print(f"   Completion Rate:     {completion_rate:.1f}%")

print(f"\n--- Status Distribution ---")
for status, count in df[status_col].value_counts().items():
    pct = count / total_orders * 100
    print(f"   {status:<35} {count:>7,} ({pct:>5.1f}%)")

# ============================================================================
# NOTEBOOK 3: VOLUME & DEMAND ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("📊 NOTEBOOK 3: VOLUME & DEMAND ANALYSIS")
print("=" * 80)

unique_orders = df['WP Order ID'].nunique()
unique_products = df['Product'].nunique()
unique_customers = df['Customer'].nunique()

print(f"\n📋 VOLUME SUMMARY:")
print(f"   Total Rows:          {total_orders:,}")
print(f"   Unique Orders:       {unique_orders:,}")
print(f"   Total Quantity:      {total_qty:,.0f}")
print(f"   Unique Products:     {unique_products:,}")
print(f"   Unique Customers:    {unique_customers:,}")

print(f"\n--- Top 10 Products by Order Volume ---")
product_vol = df['Product'].value_counts().head(10)
for product, count in product_vol.items():
    pct = count / total_orders * 100
    print(f"   {product[:45]:<45} {count:>6,} ({pct:>5.1f}%)")

print(f"\n--- Top 10 Customers by Order Volume ---")
customer_vol = df['Customer'].value_counts().head(10)
for customer, count in customer_vol.items():
    pct = count / total_orders * 100
    print(f"   {customer[:45]:<45} {count:>6,} ({pct:>5.1f}%)")

# Weekly trend
print(f"\n--- Weekly Volume Trend (Last 8 Weeks) ---")
trend_df = df[df['added_date'].notna()].copy()
trend_df['week'] = trend_df['added_date'].dt.to_period('W').dt.start_time
weekly = trend_df.groupby('week').size().reset_index(name='orders')
for _, row in weekly.tail(8).iterrows():
    print(f"   {row['week'].strftime('%Y-%m-%d'):<15} {row['orders']:>6,} orders")

# ============================================================================
# NOTEBOOK 4: QUALITY & SATISFACTION METRICS
# ============================================================================
print("\n" + "=" * 80)
print("📊 NOTEBOOK 4: QUALITY & SATISFACTION METRICS")
print("=" * 80)

itd_total = df['itd_known'].sum()
on_time = df['is_on_time'].sum()
on_time_pct = (on_time / itd_total * 100) if itd_total > 0 else 0

print(f"\n⏱️ ON-TIME DELIVERY:")
print(f"   Data Available:   {itd_total:,} orders ({itd_total/total_orders*100:.1f}% coverage)")
print(f"   On-Time:          {on_time:,}")
print(f"   On-Time Rate:     {on_time_pct:.1f}%")

print(f"\n📊 REJECTION/OBJECTION SUMMARY:")
print(f"   Rejected Orders:  {rejected:,}")
print(f"   Objected Orders:  {objected:,}")
print(f"   Total Issues:     {rejected + objected:,} ({(rejected+objected)/total_orders*100:.1f}%)")

# Rejection reasons
if 'Approved/Rejected Reason' in df.columns:
    reason_df = df[df[status_col].isin(['Rejected', 'Objected'])]
    reason_col = 'Approved/Rejected Reason'
    reasons = reason_df[reason_col].dropna()
    reasons = reasons[reasons.str.strip() != '']
    if len(reasons) > 0:
        print(f"\n--- Top Rejection/Objection Reasons ---")
        for reason, count in reasons.value_counts().head(5).items():
            print(f"   {str(reason)[:50]:<50} {count:>5}")

# ============================================================================
# NOTEBOOK 5: PROCESSING TIME ANALYSIS
# ============================================================================
print("\n" + "=" * 80)
print("📊 NOTEBOOK 5: PROCESSING TIME ANALYSIS")
print("=" * 80)

def time_stats(series, name):
    clean = series.dropna()
    clean = clean[clean >= 0]  # Remove negative values
    if len(clean) > 0:
        print(f"   {name:<25} Mean: {clean.mean():>6.1f}d  Median: {clean.median():>6.1f}d  Max: {clean.max():>6.0f}d  (n={len(clean):,})")
    else:
        print(f"   {name:<25} No data available")

print(f"\n⏱️ PROCESSING TIME SUMMARY:")
time_stats(df['time_to_ack'], "Time to Acknowledge")
time_stats(df['time_to_approve'], "Time to Approve")
time_stats(df['total_cycle'], "Total Cycle Time")

# Bottleneck
ack_mean = df['time_to_ack'].dropna().mean()
approve_mean = df['time_to_approve'].dropna().mean()
if pd.notna(ack_mean) and pd.notna(approve_mean):
    bottleneck = "Acknowledge" if ack_mean > approve_mean else "Approve"
    print(f"\n🔍 BOTTLENECK: {bottleneck} stage ({max(ack_mean, approve_mean):.1f} days avg)")

# Slowest products
print(f"\n--- Slowest Products by Avg Cycle Time (Top 10) ---")
cycle_by_product = df[df['total_cycle'].notna()].groupby('Product').agg(
    count=('total_cycle', 'count'),
    avg_cycle=('total_cycle', 'mean')
).reset_index()
cycle_by_product = cycle_by_product[cycle_by_product['count'] >= 10]
cycle_by_product = cycle_by_product.nlargest(10, 'avg_cycle')
for _, row in cycle_by_product.iterrows():
    print(f"   {row['Product'][:40]:<40} {row['avg_cycle']:>6.1f} days (n={row['count']:.0f})")

# ============================================================================
# NOTEBOOK 6: EXECUTIVE DASHBOARD SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("📊 NOTEBOOK 6: EXECUTIVE DASHBOARD SUMMARY")
print("=" * 80)

sla_compliance = 100 - breach_pct
avg_cycle = df['total_cycle'].dropna().mean()

print(f"\n" + "=" * 60)
print("  📈 KEY PERFORMANCE INDICATORS")
print("=" * 60)
print(f"  │ Total Orders:      │ {total_orders:>12,} │")
print(f"  │ SLA Compliance:    │ {sla_compliance:>11.1f}% │ {'⚠️' if sla_compliance < 70 else '✅'}")
print(f"  │ Completion Rate:   │ {completion_rate:>11.1f}% │ {'⚠️' if completion_rate < 70 else '✅'}")
print(f"  │ Approval Rate:     │ {approval_rate:>11.1f}% │ {'⚠️' if approval_rate < 70 else '✅'}")
print(f"  │ On-Time Delivery:  │ {on_time_pct:>11.1f}% │ {'⚠️' if on_time_pct < 80 else '✅'}")
print(f"  │ Avg Cycle Time:    │ {avg_cycle:>9.1f} days │")
print("=" * 60)

print(f"\n🚨 ATTENTION REQUIRED:")
print(f"   🔴 SLA Breached:        {breached_orders:,} orders")
print(f"   🟡 At Risk (≤7 days):   {at_risk_orders:,} orders")
print(f"   ❌ Rejected:            {rejected:,} orders")
print(f"   ⚠️ Objected:            {objected:,} orders")

print("\n" + "=" * 80)
print("✅ ANALYSIS COMPLETE")
print("=" * 80)

# Export summary
summary_file = 'analysis_summary_' + datetime.now().strftime('%Y%m%d_%H%M') + '.txt'
print(f"\n📁 Full report can be viewed above")
print(f"📊 For interactive charts, open the notebooks in Google Colab")
