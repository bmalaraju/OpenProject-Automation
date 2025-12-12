import pandas as pd
import json
from pathlib import Path

def extract_products(file_path: str, output_path: str):
    print(f"Reading {file_path}...")
    try:
        df = pd.read_excel(file_path)
        products = df['Product'].dropna().unique().tolist()
        products.sort()
        
        print(f"Found {len(products)} unique products.")
        
        mapping = {p: "" for p in products}
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=4)
            
        print(f"Mapping template written to {output_path}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    excel_file = "08.21.WP Orders_21-08-2025_v01 (2).xlsx"
    output_json = "src/wpr_agent/config/product_mapping.json"
    extract_products(excel_file, output_json)
