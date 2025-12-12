import pandas as pd

# Create a simple dataframe
df = pd.DataFrame({
    'Product': ['TestProduct'],
    'WP Order ID': ['ORD-001'],
    'BP ID': ['BP-001'],
    'Project Name': ['Test Project'],
    'Domain': ['Test Domain'],
    'Customer': ['Test Customer'],
    'WP ID': ['WP-001'],
    'WP Name': ['Test WP'],
    'WP Quantity': [1],
    'Employee Name': ['Test User'],
    'STD': [10],
    'WP Order Status': ['Approved'],
    'WP Requested Delivery Date': ['2025-01-01'],
    'WP Readiness Date': ['2025-01-02'],
    'PO StartDate': ['2025-01-01'],
    'PO EndDate': ['2025-12-31'],
    'Approved Date': ['2025-01-01'],
    'Submitted Date': ['2025-01-01'],
    'Cancelled Date': [''],
    'Added Date': ['2025-01-01'],
    'Updated Date': ['2025-01-01'],
    'Acknowledged Date': ['2025-01-01']
})

# Save to Excel
df.to_excel('manual_test.xlsx', sheet_name='WP_Overall_Order_Report', index=False)
print("Created manual_test.xlsx")
