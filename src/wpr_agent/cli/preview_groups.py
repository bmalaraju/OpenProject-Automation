from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd
from dotenv import load_dotenv

# Load wpr_agent .env and prepare imports
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env", override=False)

from wpr_agent.tools.excel_tools import ensure_columns, rows_from_df, groups_from_rows  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Preview WPR groups from Excel (wpr_agent)")
    ap.add_argument("--file", "-f", required=True)
    ap.add_argument("--sheet", default="Sheet1")
    args = ap.parse_args()

    try:
        df = pd.read_excel(args.file, sheet_name=args.sheet, engine="openpyxl").fillna("")
    except Exception as ex:
        print(json.dumps({"error": f"Failed to read Excel: {ex}"}, indent=2))
        raise SystemExit(1)

    df = ensure_columns(df)
    rows = rows_from_df(df)
    groups = groups_from_rows(rows)

    out: Dict[str, Any] = {
        "total_rows": len(rows),
        "group_count": len(groups),
        "groups": [],
    }
    for g in groups:
        sample = []
        for r in g.rows[:2]:
            sample.append(
                {
                    "wp_order_id": r.wp_order_id,
                    "wp_id": r.wp_id,
                    "status": r.wp_order_status,
                    "due": r.target_due_date,
                    "effective_updated": r.effective_updated_date,
                }
            )
        out["groups"].append(
            {
                "bp_id": g.bp_id,
                "project_name": g.project_name,
                "product": g.product,
                "count": len(g.rows),
                "sample": sample,
            }
        )

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

