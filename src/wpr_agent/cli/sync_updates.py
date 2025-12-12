#!/usr/bin/env python3
"""
Sync Updates CLI
================

Orchestrates the "Delta Sync" workflow for handling future updates:
1. Ingests a new Excel file into InfluxDB.
2. Runs the Router in delta-only mode to process only changed orders.

Usage:
    python sync_updates.py --file "path/to/new_file.xlsx" [--sheet "SheetName"] [--online] [--dry-run]

"""
import argparse
import sys
import os
import json
from pathlib import Path

# Bootstrap path
BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

from wpr_agent.cli.upload_excel_to_influx import ingest_file
from wpr_agent.cli.router import main as router_main

def main():
    parser = argparse.ArgumentParser(description="Delta Sync: Ingest Excel and Apply Updates")
    parser.add_argument("--file", required=True, help="Path to the new Excel file")
    parser.add_argument("--sheet", default="WP_Overall_Order_Report", help="Sheet name (default: WP_Overall_Order_Report)")
    parser.add_argument("--online", action="store_true", help="Enable online mode (apply changes to OpenProject)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate changes without applying them")
    parser.add_argument("--registry", default="config/product_project_registry.json", help="Path to registry file")
    parser.add_argument("--ingest-only", action="store_true", help="Only ingest data, do not run router")
    parser.add_argument("--no-filter", action="store_true", help="Ingest all rows, ignoring registry")
    
    args = parser.parse_args()

    # 1. Validation
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    registry_path = Path(args.registry).resolve()
    if not args.no_filter and not registry_path.exists():
        # Try relative to repo root
        registry_path = BASE_DIR / args.registry
        if not registry_path.exists():
             print(f"Error: Registry not found at {args.registry} or {registry_path}")
             sys.exit(1)

    print(f"=== Delta Sync Started ===")
    print(f"File: {file_path}")
    print(f"Mode: {'ONLINE' if args.online else 'OFFLINE'} (Dry Run: {args.dry_run})")
    if args.ingest_only:
        print("Option: Ingest Only (Router skipped)")
    if args.no_filter:
        print("Option: No Filter (Registry ignored)")

    # 2. Ingestion
    print("\n--- Step 1: Ingesting to InfluxDB ---")
    try:
        import pandas as pd
        import hashlib
        from wpr_agent.cli.upload_excel_to_influx import ingest_dataframe
        from wpr_agent.router.tools.registry import load_product_registry_tool

        allowed_products = set()
        if not args.no_filter:
            # Load registry for filtering
            registry = load_product_registry_tool(str(registry_path))
            if not registry:
                print("Warning: Registry is empty. Ingesting everything?")
            allowed_products = set(registry.keys()) if registry else set()
        
        # Read Excel
        print(f"Reading {file_path}...")
        df = pd.read_excel(file_path, sheet_name=args.sheet, engine="openpyxl").fillna("")
        
        # Filter
        if allowed_products and not args.no_filter:
            print(f"Filtering by {len(allowed_products)} products from registry...")
            original_count = len(df)
            # Find product column (case-insensitive)
            prod_col = next((c for c in df.columns if str(c).lower() == "product"), "Product")
            
            if prod_col in df.columns:
                df = df[df[prod_col].isin(allowed_products)]
                print(f"Registry Filter: Kept {len(df)} of {original_count} rows.")
            else:
                print(f"Warning: Column '{prod_col}' not found. Skipping filter.")
        
        if df.empty:
            print("No rows to ingest after filtering.")
            sys.exit(0)

        # Calculate hash
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Ingest
        res = ingest_dataframe(df, source_filename=file_path.name, file_hash=file_hash)
        if not res:
             print("Ingestion failed or returned no result.")
             sys.exit(1)
        print(f"Ingestion complete. Batch ID: {res.get('batch_id')}")
    except Exception as e:
        print(f"Ingestion Error: {e}")
        sys.exit(1)

    # 3. Router Execution (Delta Only)
    if args.ingest_only:
        print("\n=== Ingest Only Complete ===")
        sys.exit(0)

    print("\n--- Step 2: Running Router (Delta Only) ---")
    
    # Construct arguments for router.py
    router_args = [
        "--source", "influx",
        "--delta-only",
        "--registry", str(registry_path),
        "--artifact-dir", "artifacts/delta_sync",
    ]
    
    if args.online:
        router_args.append("--online")
    
    if args.dry_run:
        router_args.append("--dry-run")
        
    # Router expects args as a list of strings (excluding script name)
    try:
        router_main(router_args)
    except SystemExit as e:
        if e.code != 0:
            print(f"Router failed with exit code {e.code}")
            sys.exit(e.code)
    except Exception as e:
        print(f"Router Error: {e}")
        sys.exit(1)

    print("\n=== Delta Sync Complete ===")

if __name__ == "__main__":
    main()
