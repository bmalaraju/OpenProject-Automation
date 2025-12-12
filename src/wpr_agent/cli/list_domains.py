from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


# Bootstrap env and imports similar to other scripts
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR.parent / ".env", override=False)

def normalize_domain(name: str) -> str:
    s = (name or "").strip().upper()
    out = []
    prev_us = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
                prev_us = True
    key = "".join(out).strip("_")
    return key


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="List unique Domain values from Excel (raw and normalized)")
    ap.add_argument("--file", "-f", default=os.getenv("WORK_PACKAGE_FILE", "work_packages.xlsx"))
    ap.add_argument("--sheet", default="Sheet1")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    try:
        df = pd.read_excel(args.file, sheet_name=args.sheet, engine="openpyxl").fillna("")
    except Exception as ex:
        print(json.dumps({"error": f"Failed to read Excel: {ex}", "file": args.file, "sheet": args.sheet}, indent=2))
        raise SystemExit(1)

    # Find a domain column
    domain_col = None
    for c in df.columns:
        cn = str(c).strip().lower()
        if cn in ("domain", "domain1"):
            domain_col = c
            break
    if not domain_col:
        print(json.dumps({"error": "No 'Domain' column found", "columns": [str(c) for c in df.columns]}, indent=2))
        raise SystemExit(1)

    raw_vals = sorted({str(x).strip() for x in df[domain_col].tolist() if str(x).strip()})
    norm_vals = sorted({normalize_domain(x) for x in raw_vals})
    out = {
        "file": str(args.file),
        "sheet": args.sheet,
        "domain_column": str(domain_col),
        "unique_count": len(raw_vals),
        "raw_values": raw_vals,
        "normalized": norm_vals,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
