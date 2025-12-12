
import json
import pandas as pd
from wpr_agent.models import TrackerFieldMap
from wpr_agent.router.tools.compile_products import compile_product_bundle_tool

def test_compile():
    # 1. Load overrides
    with open("config/op_field_id_overrides.json", "r") as f:
        overrides = json.load(f)
    print(f"Loaded {len(overrides)} overrides.")
    
    fmap = TrackerFieldMap(discovered_custom_fields=overrides)
    
    # 2. Create dummy DF
    # Based on debug output for WPO00187674
    data = {
        "WP Order ID": ["WPO00187674"],
        "Product": ["FlowOne"],
        "Project Name": ["FlowOne"],
        "Domain": ["Flowone"],
        "Customer": ["TestCustomer"],
        "WP ID": ["WP123"],
        "WP Name": ["Test WP"],
        "WP Quantity": [1],
        "WP Order Status": ["Approved"],
        "STD": ["10.0"],
        "Updated Date": ["2025-12-01T10:00:00Z"],
        "WP Readiness Date": ["2025-12-05T10:00:00Z"]
    }
    df = pd.DataFrame(data)
    
    # 3. Call compile
    print("Calling compile_product_bundle_tool...")
    bundle = compile_product_bundle_tool(
        product="FlowOne",
        project_key="FlowOne",
        fieldmap=fmap,
        order_groups=[("WPO00187674", df)]
    )
    
    # 4. Inspect result
    print(f"Bundle created with {len(bundle.product_plans)} plans.")
    if bundle.product_plans:
        plan = bundle.product_plans[0]
        epic = plan.epic.plan
        print(f"Epic Summary: {epic.summary}")
        print(f"Epic Fields keys: {list(epic.fields.keys())}")
        
        # Check specific fields
        # customField2 = WPR WP Order ID
        print(f"customField2 (Order ID): {epic.fields.get('customField2')}")
        # customField23 = WPR STD
        print(f"customField23 (STD): {epic.fields.get('customField23')}")
        
        # Check if empty
        if not epic.fields:
            print("CRITICAL: Epic fields are empty!")
        else:
            print("Epic fields populated.")

if __name__ == "__main__":
    test_compile()
