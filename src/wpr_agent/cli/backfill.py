import argparse
import sys
import time
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict
import pandas as pd
import traceback
from datetime import datetime

from wpr_agent.shared import influx_helpers
from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2
from wpr_agent.services.provider import make_service
from wpr_agent.models import TrackerFieldMap
from dotenv import load_dotenv

# Graph Tools
from wpr_agent.router.tools.compile_products import compile_product_bundle_tool
# Direct local apply (Bypassing MCP/httpx)
from wpr_agent.cli.apply_plan import apply_bp

def load_product_mapping() -> Dict[str, str]:
    try:
        # Look in config/product_project_registry.json (root/config)
        base = Path(__file__).resolve().parents[3] / "config" / "product_project_registry.json"
        if not base.exists():
             # Fallback: maybe we are not in src/wpr_agent/cli?
             base = Path("config/product_project_registry.json").resolve()
        
        if not base.exists():
            print(f"Warning: Registry file not found at {base}")
            return {}

        with open(base, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data.get("registry", {})
    except Exception as e:
        print(f"Warning: Could not load product mapping: {e}")
        return {}

def ensure_report_dir() -> Path:
    root = Path(__file__).resolve().parents[3]
    report_dir = root / "reports"
    report_dir.mkdir(exist_ok=True)
    return report_dir

def write_report(report_dir: Path, batch_id: str, summary: Dict[str, Any], details: List[Dict[str, Any]]):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backfill_report_{batch_id}_{timestamp}.json"
    path = report_dir / filename
    
    data = {
        "batch_id": batch_id,
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "details": details
    }
    
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"\nReport written to: {path}")
    except Exception as e:
        print(f"Error writing report: {e}")

import concurrent.futures
import threading

# Thread-safe lock for printing
print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)

def process_order(
    svc: Optional[OpenProjectServiceV2],
    prod: str,
    oid: str,
    lst: List[Dict[str, Any]],
    mapping: Dict[str, str],
    default_project_key: Optional[str],
    fieldmap: TrackerFieldMap,
    dry_run: bool
) -> Dict[str, Any]:
    
    order_report = {
        "order_id": oid,
        "product": prod,
        "status": "pending",
        "errors": [],
        "warnings": [],
        "created": {},
        "updated": []
    }

    try:
        # Resolve Project Key
        target_key = mapping.get(prod) or default_project_key
        if not target_key:
            safe_print(f"[{oid}] Skipped: No project mapping for product '{prod}' and no default key.")
            order_report["status"] = "skipped"
            order_report["warnings"].append("No project mapping")
            return order_report
        
        order_report["project_key"] = target_key

        # Convert list of dicts back to DataFrame for the tool
        sub_df = pd.DataFrame(lst)
        order_groups = [(oid, sub_df)]

        # Compile Bundle
        bundle = compile_product_bundle_tool(prod, target_key, fieldmap, order_groups)
        
        if not bundle.product_plans:
            safe_print(f"[{oid}] Warning: No plans compiled.")
            order_report["status"] = "skipped"
            order_report["warnings"].append("No plans compiled")
            return order_report

        # Apply Plans
        for plan in bundle.product_plans:
            if dry_run:
                safe_print(f"[{oid}] Dry Run: Would apply plan for {plan.bp_id}")
                order_report["status"] = "dry_run"
                continue

            # Direct call to apply_bp (No MCP)
            if hasattr(plan, "model_dump"):
                payload = plan.model_dump()
            elif hasattr(plan, "dict"):
                payload = plan.dict()
            else:
                payload = plan

            created, warnings, errors, stats, timings = apply_bp(
                svc=svc,
                bundle_domain=prod,
                project_key=target_key,
                fieldmap=fieldmap,
                bp_plan=payload,
                max_retries=3,
                backoff_base=0.5,
                dry_run=False
            )

            if errors:
                safe_print(f"[{oid}] Errors: {errors}")
                order_report["errors"].extend(errors)
                order_report["status"] = "failed"
            
            if warnings:
                for w in warnings:
                    safe_print(f"[{oid}] Warning: {w}")
                order_report["warnings"].extend(warnings)

            if created.get("epics"):
                safe_print(f"[{oid}] Created Epics: {created['epics']}")
                order_report["created"]["epics"] = created["epics"]
            if created.get("stories"):
                safe_print(f"[{oid}] Created Stories: {created['stories']}")
                order_report["created"]["stories"] = created["stories"]
            if created.get("updated"):
                safe_print(f"[{oid}] Updated: {created['updated']}")
                order_report["updated"] = created["updated"]
            
            if not errors:
                order_report["status"] = "success"

    except Exception as e:
        safe_print(f"[{oid}] Exception: {e}")
        traceback.print_exc()
        order_report["status"] = "exception"
        order_report["errors"].append(str(e))
    
    return order_report

def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Day Zero Backfill for WPR Orders (Optimized)")
    parser.add_argument("--file", required=True, help="Path to Excel file")
    parser.add_argument("--sheet", default="Sheet1", help="Sheet name")
    parser.add_argument("--batch-id", default=f"backfill-{int(time.time())}", help="Batch ID")
    parser.add_argument("--project-key", help="Default OpenProject Project Key (fallback)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to OpenProject")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip InfluxDB ingestion")
    parser.add_argument("--filter-existing", action="store_true", help="Filter Excel rows by existing OpenProject subprojects")
    parser.add_argument("--ingest-only", action="store_true", help="Exit after InfluxDB ingestion")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of orders to process")
    parser.add_argument("--order-id", help="Filter by specific Order ID")
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel workers")
    args = parser.parse_args()

    print(f"Starting backfill for {args.file}...")
    
    mapping = load_product_mapping()
    if mapping:
        print(f"Loaded {len(mapping)} product mappings.")
    else:
        print("No product mapping loaded. Will rely on --project-key.")

    if not mapping and not args.project_key:
        print("Error: No product mapping found and no --project-key provided.")
        sys.exit(1)

    # 1. Ingest
    if not args.skip_ingest:
        print("Reading Excel file...")
        try:
            df = pd.read_excel(args.file, sheet_name=args.sheet)
        except Exception as e:
            print(f"Error reading Excel: {e}")
            sys.exit(1)

        # Preprocess (Optional)
        if args.filter_existing:
            print("Filtering rows by existing OpenProject subprojects...")
            from wpr_agent.tools.preprocess_excel import filter_wpr_dataframe
            try:
                df = filter_wpr_dataframe(df)
            except Exception as e:
                print(f"Filtering failed: {e}")
                sys.exit(1)
        
        # Filter by Product Registry
        if mapping:
            print("Filtering rows by Product Registry...")
            original_count = len(df)
            allowed_products = set(mapping.keys())
            prod_col = next((c for c in df.columns if c.lower() == "product"), "Product")
            
            if prod_col in df.columns:
                df = df[df[prod_col].isin(allowed_products)]
                print(f"Registry Filter: Kept {len(df)} of {original_count} rows.")
            else:
                print("Warning: 'Product' column not found for filtering. Skipping registry filter.")

        if df.empty:
            print("No rows remaining after filtering. Exiting.")
            sys.exit(0)
        
        print(f"Ingesting {len(df)} rows to InfluxDB...")
        try:
            from wpr_agent.cli.upload_excel_to_influx import ingest_dataframe
            import hashlib
            with open(args.file, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            
            ingest_dataframe(df, batch_id=args.batch_id, source_filename=os.path.basename(args.file), file_hash=file_hash)
        except Exception as e:
            print(f"Ingestion failed: {e}")
            sys.exit(1)
    else:
        print("Skipping ingestion as requested.")

    if args.ingest_only:
        print("Ingestion complete. Exiting as requested.")
        sys.exit(0)

    # 2. Query
    print("Querying rows...")
    df = influx_helpers.query_wpr_rows(batch_id=args.batch_id)
    if df is None or df.empty:
        print("No rows found.")
        sys.exit(0)
    
    rows = df.to_dict(orient="records")
    print(f"Found {len(rows)} rows.")

    # 3. Group by Order ID (BP ID)
    grouped = defaultdict(list)
    for r in rows:
        oid = str(r.get("WP Order ID") or r.get("order_id") or "")
        prod = str(r.get("Product") or r.get("product") or "")
        if oid and prod:
            grouped[(prod, oid)].append(r)

    print(f"Processing {len(grouped)} unique orders...")

    # Load Field Map
    field_map_path = Path(__file__).resolve().parents[3] / "config" / "op_field_id_overrides.json"
    custom_options_path = Path(__file__).resolve().parents[3] / "config" / "op_custom_option_overrides.json"
    os.environ["OP_FIELD_ID_OVERRIDES_PATH"] = str(field_map_path)
    os.environ["OP_CUSTOM_OPTION_OVERRIDES_PATH"] = str(custom_options_path)
    custom_fields = {}
    if field_map_path.exists():
        try:
            with open(field_map_path, "r") as f:
                custom_fields = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load field map: {e}")
    
    fieldmap = TrackerFieldMap(discovered_custom_fields=custom_fields)
    
    # Initialize Service
    svc = None
    if not args.dry_run:
        try:
            svc = make_service()
            # Pre-warm caches
            print("Pre-warming service caches...")
            svc._cf_map() # Custom fields
            svc._get_global_options_map() # Custom options
            # Pre-warm project IDs and Types for known products
            for prod, pkey in mapping.items():
                try:
                    pid = svc._project_id(pkey)
                    if pid:
                        svc._types_for(pkey)
                        # Warm form schemas for Epic/Story
                        tid_epic = svc._type_id(pkey, "Epic")
                        if tid_epic:
                            svc._get_form_schema(pid, tid_epic)
                        tid_story = svc._type_id(pkey, "Story")
                        if tid_story:
                            svc._get_form_schema(pid, tid_story)
                except Exception:
                    pass
            print("Caches warmed.")
        except Exception as e:
            print(f"Error initializing OpenProject service: {e}")
            sys.exit(1)

    # 4. Process with ThreadPoolExecutor
    processed_count = 0
    skipped_count = 0
    error_count = 0
    report_details = []

    # Filter items first if needed
    items_to_process = []
    for (prod, oid), lst in grouped.items():
        if args.order_id and oid != args.order_id:
            continue
        items_to_process.append(((prod, oid), lst))

    if args.limit > 0:
        items_to_process = items_to_process[:args.limit]

    print(f"Starting processing of {len(items_to_process)} orders with {args.workers} workers...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_order, 
                svc, prod, oid, lst, mapping, args.project_key, fieldmap, args.dry_run
            ): (prod, oid) 
            for ((prod, oid), lst) in items_to_process
        }

        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                report_details.append(result)
                
                status = result.get("status")
                if status == "success" or status == "dry_run":
                    processed_count += 1
                elif status == "skipped":
                    skipped_count += 1
                else:
                    error_count += 1
            except Exception as exc:
                print(f"Worker exception: {exc}")
                error_count += 1

    print(f"\nDone. Processed: {processed_count}, Skipped: {skipped_count}, Errors: {error_count}")
    
    # Generate Report
    summary = {
        "total_orders_found": len(grouped),
        "processed": processed_count,
        "skipped": skipped_count,
        "errors": error_count,
        "args": vars(args)
    }
    write_report(ensure_report_dir(), args.batch_id, summary, report_details)

if __name__ == "__main__":
    main()
