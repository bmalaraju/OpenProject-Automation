from __future__ import annotations

"""
Delta Apply from Influx

Reads normalized rows from Influx (wpr_input), computes per-order source fingerprints,
compares with the last stored src_hash, and for changed orders only executes:
  compile → validate → (apply) → update src_hash

Provider-aware (OpenProject or Jira) via existing services. Default is dry-run unless --online.

Example:
  python wpr_agent/scripts/delta_apply_influx.py \
    --since 12h --registry wpr_agent/config/product_project_registry.json --dry-run

  python wpr_agent/scripts/delta_apply_influx.py \
    --batch-id 20241104T0800 --registry wpr_agent/config/product_project_registry.json --online
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

# Bootstrap env and paths (mirror other scripts)
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BASE_DIR.parent.parent / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wpr_agent.router.tools.influx_source import read_influx_df_tool, group_product_order_from_df_tool  # type: ignore
from wpr_agent.router.tools.registry import load_product_registry_tool  # type: ignore
from wpr_agent.router.tools.discovery import discover_fieldmap_tool  # type: ignore
from wpr_agent.router.tools.compile_products import compile_product_bundle_tool  # type: ignore
from wpr_agent.router.tools.validate import validate_bundle_tool, decide_apply_tool  # type: ignore
# Direct local apply (Bypassing MCP/httpx)
from wpr_agent.cli.apply_plan import apply_bp
from wpr_agent.state.influx_store import InfluxStore  # type: ignore
from wpr_agent.models import TrackerFieldMap

import concurrent.futures


def parse_args(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Delta apply from Influx (compile→validate→apply changed orders)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--since", help="Flux range start (e.g., 12h, 3d). Default 7d", default="7d")
    src.add_argument("--batch-id", help="Filter points by batch_id tag")
    ap.add_argument("--measurement", default="wpr_input", help="Influx measurement for input rows")
    ap.add_argument("--registry", default=str(Path(__file__).resolve().parents[3] / "config" / "product_project_registry.json"))
    ap.add_argument("--online", action="store_true", help="Apply changes to provider (OpenProject/Jira)")
    ap.add_argument("--dry-run", action="store_true", help="Force dry-run (no writes); overrides --online")
    ap.add_argument("--continue-on-error", action="store_true", help="Apply only passing orders when validation errors exist")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--backoff-base", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=5, help="Number of parallel workers")
    ap.add_argument("--force", action="store_true", help="Force update even if unchanged")
    ap.add_argument("--artifact-dir")
    ap.add_argument("--report")
    ap.add_argument("--summary")
    ap.add_argument("--ingest-file", help="Path to Excel file to ingest before processing")
    ap.add_argument("--sheet", default="WP_Overall_Order_Report", help="Sheet name for ingestion (default: WP_Overall_Order_Report)")
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    # Handle Ingestion if requested
    if args.ingest_file:
        print(f"Ingesting file: {args.ingest_file} (Sheet: {args.sheet})")
        from wpr_agent.shared.influx_helpers import ingest_excel_to_influx
        
        # Generate batch_id if not provided
        if not args.batch_id:
            args.batch_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            print(f"Generated batch_id: {args.batch_id}")
            
        try:
            ingest_excel_to_influx(Path(args.ingest_file), sheet=args.sheet, batch_id=args.batch_id)
            print(f"Ingestion complete for batch_id: {args.batch_id}")
        except Exception as e:
            print(f"Error during ingestion: {e}")
            return

    # Decide dry-run
    dry_run = True
    if args.online and not args.dry_run:
        dry_run = False

    # Load product→project registry
    registry = load_product_registry_tool(args.registry)

    # Read Influx → DataFrame
    df = read_influx_df_tool(since=args.since if not args.batch_id else None, batch_id=args.batch_id, measurement=args.measurement)
    if df is None or len(df) == 0:
        print(json.dumps({"ok": True, "message": "no-input-rows"}, indent=2))
        return
    
    print(f"DEBUG: Loaded DF with {len(df)} rows.")
    print(f"DEBUG: DF columns: {list(df.columns)}")
    print(f"DEBUG: DF head:\n{df.head().to_string()}")
    
    # Check for failing order in DF
    failing = df[df["WP Order ID"] == "WPO00187674"]
    if not failing.empty:
        print(f"DEBUG: Failing order found in DF:\n{failing.to_string()}")
    else:
        print("DEBUG: Failing order WPO00187674 NOT found in DF!")

    # Group by Product → Order ID
    grouped = group_product_order_from_df_tool(df)

    # Prepare state
    store = InfluxStore()
    totals = {"orders": 0, "orders_changed": 0, "created": 0, "updated": 0, "warnings": 0, "failures": 0, "retries": 0, "dropped_assignees": 0}
    domains: List[Dict[str, Any]] = []
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = Path(args.report) if args.report else None
    summary_path = Path(args.summary) if args.summary else None
    artifacts_dir = Path(args.artifact_dir) if args.artifact_dir else None
    if artifacts_dir:
        (artifacts_dir).mkdir(parents=True, exist_ok=True)

    # Iterate products
    for product, order_list in grouped:
        project_key = registry.get(str(product).strip())
        if not project_key:
            domains.append({"domain": product, "project_key": None, "order_count": len(order_list), "changed": 0, "created_epics": [], "created_stories": [], "updated": [], "warnings": [f"No project mapping for product '{product}'"], "failures": []})
            totals["warnings"] += 1
            continue
        # Discover fieldmap
        print(f"Processing product '{product}' with {len(order_list)} orders...")
        
        # Load field map from override file (like backfill.py does)
        field_map_path = Path(__file__).resolve().parents[3] / "config" / "op_field_id_overrides.json"
        custom_options_path = Path(__file__).resolve().parents[3] / "config" / "op_custom_option_overrides.json"
        os.environ["OP_FIELD_ID_OVERRIDES_PATH"] = str(field_map_path)
        os.environ["OP_CUSTOM_OPTION_OVERRIDES_PATH"] = str(custom_options_path)
        
        custom_fields =  {}
        if field_map_path.exists():
            try:
                with open(field_map_path, "r") as f:
                    custom_fields = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load field map: {e}")
        
        fmap = TrackerFieldMap(discovered_custom_fields=custom_fields)
        print(f"Field map loaded: {len(custom_fields)} custom fields.")

        # Compute delta set per order using content hashing (fingerprinting)
        print(f"Checking content hashes for {len(order_list)} orders (with --force={args.force})...")
        changed: Set[str] = set()
        
        from wpr_agent.router.tools.influx_source import compute_order_src_hash
        
        if args.force:
            # When force is enabled, skip all checks and process all orders
            for idx, (order_id, sub) in enumerate(order_list):
                if idx % 100 == 0:
                    print(f"  Marking {idx}/{len(order_list)} orders as changed (force mode)...")
                if str(order_id or "").strip():
                    changed.add(str(order_id))
            print(f"Marked ALL {len(changed)} orders as changed (force mode).")
        else:
            # Hash-based mode: compare computed hash with stored hash
            for idx, (order_id, sub) in enumerate(order_list):
                if idx % 100 == 0:
                    print(f"  Checked {idx}/{len(order_list)} orders...")
                
                oid = str(order_id or "").strip()
                if not oid:
                    continue
                
                # Compute current hash
                curr_hash = compute_order_src_hash(str(product or ""), sub)
                
                # Get stored hash
                last_hash = store.get_source_hash(project_key, oid)
                
                if last_hash != curr_hash:
                    changed.add(oid)
                
                if "WPO00187674" in oid or "WPO00187539" in oid or "WPO00182554" in oid or "WPO00182556" in oid or "WPO00187244" in oid:
                    changed.add(oid)
                    print(f"DEBUG: Forcing change for {oid}")
                    
            print(f"Found {len(changed)} changed orders out of {len(order_list)} total.")

        totals["orders"] += len(order_list)
        totals["orders_changed"] += len(changed)
        # Nothing to do for this product
        if not changed:
            domains.append({"domain": product, "project_key": project_key, "order_count": len(order_list), "changed": 0, "created_epics": [], "created_stories": [], "updated": [], "warnings": [], "failures": []})
            continue

        # Build bundle for all orders in this product
        # Filter order_list to only changed orders
        changed_orders = [o for o in order_list if str(o[0]) in changed]
        
        print(f"Compiling bundle for product '{product}' with {len(changed_orders)} changed orders out of {len(order_list)} total...")
        bundle = compile_product_bundle_tool(str(product or ""), project_key, fmap, changed_orders)
        print(f"Compiled {len(bundle.product_plans or [])} plans. Validating...")
        # Validate bundle
        rep = validate_bundle_tool(bundle, fmap)
        allowed, blocked = decide_apply_tool(rep, continue_on_error=bool(args.continue_on_error))
        print(f"Validation complete. Allowed: {len(allowed) if allowed else 'all'}, Blocked: {len(blocked) if blocked else '0'}")

        created_epics: List[str] = []
        created_stories: List[str] = []
        updated_issues: List[str] = []
        warnings: List[str] = []
        failures: List[str] = []

        # Build a lookup of plan by bp_id (order_id)
        plans_by_id: Dict[str, Any] = {getattr(pp, 'bp_id', ''): pp for pp in (bundle.product_plans or [])}

        # Create service only when online
        svc = None
        epics_cache = {}
        if not dry_run:
            print("Initializing OpenProject service...")
            try:
                from wpr_agent.services.provider import make_service  # type: ignore
                svc = make_service()
                print("Service initialized successfully.")
                
                # Bulk fetch Epics to optimize performance
                print(f"Bulk fetching Epics for project '{project_key}'...")
                try:
                    epics_cache = svc.fetch_epics_map(project_key, fmap)
                    print(f"Fetched {len(epics_cache)} Epics from OpenProject.")
                except Exception as ex:
                    print(f"Warning: Bulk fetch failed, falling back to individual fetch: {ex}")
                    epics_cache = {}
            except Exception as ex:
                print(f"Failed to initialize service: {ex}")
                svc = None

        # Create a map of order_id -> sub_df for hash computation after success
        order_map = {str(o[0]): o[1] for o in changed_orders}

        # Apply per changed order id if allowed
        
        def _process_one_order(oid: str, pp: Any) -> Tuple[str, Dict[str, Any], List[str], List[str], Dict[str, int], Dict[str, float]]:
            # Helper for parallel execution
            try:
                # Convert Pydantic model to dict if needed
                if hasattr(pp, "model_dump"):
                    payload = pp.model_dump()
                elif hasattr(pp, "dict"):
                    payload = pp.dict()
                else:
                    payload = pp
                
                created, warns, errs, stats, timings = apply_bp(
                    svc,
                    bundle_domain=str(product or ""),
                    project_key=project_key,
                    fieldmap=fmap,
                    bp_plan=payload,
                    max_retries=int(args.max_retries),
                    backoff_base=float(args.backoff_base),
                    dry_run=bool(dry_run),
                    pre_fetched_epics=epics_cache,
                )
                
                # If successful and online, update the source hash
                if not dry_run and not errs and oid in order_map:
                    try:
                        h = compute_order_src_hash(str(product or ""), order_map[oid])
                        store.set_source_hash(project_key, oid, h)
                    except Exception as e:
                        print(f"Warning: Failed to update source hash for {oid}: {e}")

                return oid, created, warns, errs, stats, timings
            except Exception as e:
                return oid, {}, [], [str(e)], {}, {}

        # Prepare items
        items_to_process = []
        for oid in sorted(changed):
            if allowed and (oid not in allowed):
                warnings.append(f"Order '{oid}' blocked by validation policy")
                totals["warnings"] += 1
                continue
            pp = plans_by_id.get(oid)
            if pp is None:
                continue
            items_to_process.append((oid, pp))

        # Execute in parallel
        print(f"Processing {len(items_to_process)} orders for product '{product}' with {args.workers} workers...")
        processed_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(_process_one_order, oid, pp): oid for oid, pp in items_to_process}
            
            for future in concurrent.futures.as_completed(futures):
                oid = futures[future]
                try:
                    _, created, warns, errs, stats, timings = future.result()
                    
                    processed_count += 1
                    if errs:
                        print(f"[{processed_count}/{len(items_to_process)}] Processed order {oid}: epics={len(created.get('epics', []))}, stories={len(created.get('stories', []))}, errors={len(errs)}")
                        print(f"  ERROR: {errs[0] if errs else 'Unknown'}")
                    else:
                        print(f"[{processed_count}/{len(items_to_process)}] Processed order {oid}: epics={len(created.get('epics', []))}, stories={len(created.get('stories', []))}")
                    
                    created_epics.extend(created.get("epics", []))
                    created_stories.extend(created.get("stories", []))
                    updated_issues.extend(created.get("updated", []))
                    warnings.extend(warns)
                    failures.extend(errs)
                    totals["retries"] += int(stats.get("retries", 0))
                    totals["dropped_assignees"] += int(stats.get("dropped_assignees", 0))
                    totals["warnings"] += len(warns)
                    totals["failures"] += len(errs)
                    
                    # If successful (no failure for this order) and not dry-run, persist last processed timestamp
                    if not dry_run and not errs:
                        try:
                            last_data = store.get_last_row_time(str(product or ""), str(oid), since=args.since if not args.batch_id else None, batch_id=args.batch_id)
                            if last_data:
                                store.set_last_processed_time(project_key, str(oid), last_data)
                        except Exception:
                            pass
                except Exception as exc:
                    failures.append(f"Order {oid} failed with exception: {exc}")
                    totals["failures"] += 1

        domains.append({
            "domain": product,
            "project_key": project_key,
            "order_count": len(order_list),
            "changed": len(changed),
            "created_epics": created_epics,
            "created_stories": created_stories,
            "updated": updated_issues,
            "warnings": warnings,
            "failures": failures,
        })

    # Aggregate totals from all domains
    for domain in domains:
        totals["created"] += len(domain.get("created_epics", [])) + len(domain.get("created_stories", []))
        totals["updated"] += len(domain.get("updated", []))

    # Build run report
    run = {
        "run_id": run_id,
        "mode": {"online": bool(args.online), "dry_run": bool(dry_run)},
        "domains": domains,
        "totals": totals,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }

    if report_path:
        report_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    if summary_path:
        lines: List[str] = []
        lines.append(f"Delta Apply {run['run_id']} mode={'online' if not dry_run else 'dry-run'}")
        lines.append(f"Totals: orders={totals['orders']} changed={totals['orders_changed']} created={totals['created']} updated={totals['updated']} warnings={totals['warnings']} failures={totals['failures']} retries={totals['retries']}")
        for d in domains:
            lines.append(f"- {d['domain']} [{d['project_key']}]: orders={d['order_count']} changed={d['changed']} created(epics={len(d['created_epics'])}, stories={len(d['created_stories'])}) updated={len(d['updated'])} warnings={len(d['warnings'])} failures={len(d['failures'])}")
        summary_path.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(run, indent=2))


if __name__ == "__main__":
    main()
