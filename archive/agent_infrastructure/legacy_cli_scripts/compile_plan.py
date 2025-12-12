from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import load_dotenv

# Bootstrap env and paths
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wpr_agent.tools.excel_tools import ensure_columns
from wpr_agent.models import JiraFieldMap
from wpr_agent.router.tools.compile_products import compile_product_bundle_tool
from wpr_agent.router.tools.registry import load_product_registry_tool

try:
    # Optional import; only used when online discovery requested
    from wpr_agent.services.provider import make_service  # type: ignore
except Exception:  # pragma: no cover
    make_service = None  # type: ignore


# Domain BP grouping deprecated; compile by Product instead


def main() -> None:
    ap = argparse.ArgumentParser(description="Compile PlanBundles by Product (Epic per Order ID, Stories per quantity).")
    ap.add_argument("--file", "-f", required=True)
    ap.add_argument("--sheet", default="AN")
    ap.add_argument("--project", "-p", required=False, help="Override: compile all products to this single project key.")
    ap.add_argument("--registry", default=str(BASE_DIR / "config" / "product_project_registry.json"), help="Product→Project registry JSON.")
    ap.add_argument("--offline", action="store_true", help="Do not call provider; compile with empty field map.")
    ap.add_argument("--output", "-o", required=False, help="Write JSON PlanBundle list to this file instead of stdout.")
    args = ap.parse_args()

    # Optional: hands-free client_credentials prefetch
    try:
        if os.getenv("OPENPROJECT_CC_AUTO") == "1":
            from wpr_agent.auth.op_cc import fetch_client_credentials_token  # type: ignore
            res = fetch_client_credentials_token()
            if not res.get("ok"):
                # Non-fatal: continue; downstream may still have a valid token
                pass
    except Exception:
        pass

    # Read Excel
    try:
        df = pd.read_excel(args.file, sheet_name=args.sheet, engine="openpyxl").fillna("")
    except Exception as ex:
        print(json.dumps({"error": f"Failed to read Excel: {ex}"}, indent=2))
        raise SystemExit(1)

    df = ensure_columns(df)

    reg = load_product_registry_tool(args.registry)

    bundles: List[Dict[str, Any]] = []
    summary_warnings: List[str] = []

    # Best-effort ingest source rows into Influx if configured (non-fatal)
    try:
        from wpr_agent.state.influx_store import InfluxStore  # type: ignore
        if all(os.getenv(k) for k in ("INFLUX_URL","INFLUX_TOKEN","INFLUX_ORG","INFLUX_BUCKET")):
            try:
                store = InfluxStore()
                for _, r in df.iterrows():
                    d = {k: ("" if pd.isna(r.get(k, "")) else r.get(k, "")) for k in df.columns}
                    project_key_hint = args.project or ""
                    order_id = str(d.get("WP Order ID", ""))
                    wp_id = str(d.get("WP ID", ""))
                    store.write_wpr_row(project_key_hint, order_id, wp_id, d)
            except Exception:
                pass
    except Exception:
        pass

    # Optional fieldmap discovery
    svc = None
    if not args.offline and not args.project:
        # Only instantiate Jira when we need to discover multiple projects
        try:
            svc = make_service() if make_service else None
        except Exception:
            svc = None

    # Iterate Product -> Order ID
    for prod_val, prod_df in df.groupby("Product", dropna=False):
        product = str(prod_val or "").strip() or "Default"
        project_key = args.project or reg.get(product, reg.get("Default", ""))
        if not project_key:
            summary_warnings.append(f"No project mapping for product '{product}'. Skipping.")
            continue
        # Discover fieldmap per project unless offline
        if args.offline:
            fmap = JiraFieldMap()
        else:
            try:
                if svc is None:
                    svc = make_service() if make_service else None
                fmap = svc.discover_fieldmap(project_key) if svc else JiraFieldMap()
                # Guard for OP provider: ensure discovered IDs are OP-style
                try:
                    prov = os.getenv("TRACKER_PROVIDER", "jira").strip().lower()
                    if prov == "openproject":
                        ids = list((fmap.discovered_custom_fields or {}).values())
                        bad = [i for i in ids if isinstance(i, str) and i.startswith("customfield_")]
                        if bad and os.getenv("OP_ALLOW_MIXED", "0") != "1":
                            print(json.dumps({"error": "OpenProject discovery returned Jira-style IDs; aborting compile.", "project_key": project_key, "bad_ids": bad}, indent=2))
                            raise SystemExit(3)
                except Exception:
                    pass
            except Exception:
                fmap = JiraFieldMap()
                summary_warnings.append(f"Fieldmap discovery failed for project {project_key}; compiling with empty map.")
        # Group by Order ID
        order_groups = [(str(order or ""), sub) for order, sub in prod_df.groupby("WP Order ID", dropna=False)]
        bundle = compile_product_bundle_tool(product, project_key, fmap, order_groups)
        try:
            bundles.append(bundle.model_dump())  # type: ignore[attr-defined]
        except Exception:
            bundles.append(bundle.dict())

    out = {"bundles": bundles, "warnings": summary_warnings}
    if args.output:
        Path(args.output).write_text(json.dumps(out, indent=2), encoding="utf-8")
    else:
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
