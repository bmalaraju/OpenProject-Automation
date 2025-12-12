import pandas as pd
import os
import sys
from pathlib import Path
from typing import List, Optional, Set

# Add src to path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from wpr_agent.clients.openproject_client import OpenProjectClient
from wpr_agent.cli.backfill import load_product_mapping

def get_valid_projects(client: OpenProjectClient, parent_id: Optional[str] = None) -> Set[str]:
    """Fetch all subprojects under the parent project."""
    print("Fetching projects from OpenProject...")
    projects = client.list_projects()
    valid_keys = set()
    
    parent_href_suffix = f"/projects/{parent_id}" if parent_id else None

    for p in projects:
        # If parent_id is specified, filter by it
        if parent_href_suffix:
            parent_link = (p.get("_links") or {}).get("parent", {}).get("href")
            if not parent_link or not parent_link.endswith(parent_href_suffix):
                continue
        
        # Add both identifier and name as valid keys
        ident = p.get("identifier")
        name = p.get("name")
        if ident:
            valid_keys.add(ident.lower())
        if name:
            valid_keys.add(name.lower())
            
    print(f"Found {len(valid_keys)} valid project identifiers/names.")
    return valid_keys

def filter_wpr_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Filter DataFrame rows based on valid OpenProject subprojects."""
    # Load mapping
    mapping = load_product_mapping()
    
    # Initialize OpenProject client
    client = OpenProjectClient()
    parent_project = client.parent_project
    
    if not parent_project:
        print("Warning: OPENPROJECT_PARENT_PROJECT not set. Fetching ALL projects.")
    else:
        # Resolve parent ID if it's an identifier
        p_obj = client.resolve_project(parent_project)
        if p_obj:
            parent_id = str(p_obj.get("id"))
            print(f"Resolved parent project '{parent_project}' to ID {parent_id}")
        else:
            print(f"Error: Could not resolve parent project '{parent_project}'")
            return df

    valid_projects = get_valid_projects(client, parent_id if 'parent_id' in locals() else None)
    
    # Filter DataFrame
    def is_valid(row):
        product = str(row.get("Product", "")).strip()
        # Check mapping first
        mapped_key = mapping.get(product)
        if mapped_key:
            return mapped_key.lower() in valid_projects
        # Fallback to product name itself (if it matches a project name/id)
        return product.lower() in valid_projects

    print("Filtering rows...")
    initial_count = len(df)
    df_filtered = df[df.apply(is_valid, axis=1)]
    final_count = len(df_filtered)
    
    print(f"Filtered {initial_count} rows down to {final_count} rows.")
    return df_filtered

def preprocess_excel(input_file: str, sheet_name: str, output_file: str):
    print(f"Reading {input_file}...")
    df = pd.read_excel(input_file, sheet_name=sheet_name)
    df_filtered = filter_wpr_dataframe(df)
    
    if len(df_filtered) > 0:
        print(f"Saving to {output_file}...")
        df_filtered.to_excel(output_file, index=False, sheet_name=sheet_name)
        print("Done.")
    else:
        print("Warning: No rows remained after filtering.")

if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Preprocess Excel file for WPR Agent")
    parser.add_argument("--file", required=True, help="Input Excel file")
    parser.add_argument("--sheet", default="Sheet1", help="Sheet name")
    parser.add_argument("--output", required=True, help="Output Excel file")
    
    args = parser.parse_args()
    
    preprocess_excel(args.file, args.sheet, args.output)
