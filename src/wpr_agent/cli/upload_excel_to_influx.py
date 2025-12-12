from __future__ import annotations

"""
Upload normalized Excel rows to an InfluxDB bucket as time-series points (InfluxDB 3 / SQL).

Env required:
  INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

Usage:
  - Explicit file:
      python wpr_agent/scripts/upload_excel_to_influx.py --file work_packages.xlsx --sheet Sheet1
  - Latest from directory (by mtime) with pattern:
      python wpr_agent/scripts/upload_excel_to_influx.py --dir C:\\data\\wpr --pattern "work_packages*.xlsx" --sheet Sheet1

Measurement: wpr_input
Tags: product, order_id, bp_id, project_name, domain, customer, batch_id
Fields: all remaining normalized fields as strings/ints, plus source_filename and file_hash on each point
Additional summary measurement: ingestion_run (fields: file_hash, source_filename, rows; tag: batch_id)
"""

import argparse
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from dotenv import load_dotenv
import sys
import time

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(BASE_DIR.parent / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

# Local implementation of ensure_columns (replacing missing wpr_agent.tools.excel_tools)
def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure standard columns exist in DataFrame."""
    required = [
        "Product", "WP Order ID", "BP ID", "Project Name", "Domain", "Customer",
        "WP ID", "WP Name", "WP Quantity", "Employee Name", "STD",
        "WP Order Status", "WP Requested Delivery Date", "WP Readiness Date",
        "PO StartDate", "PO EndDate", "Approved Date", "Submitted Date",
        "Cancelled Date", "Added Date", "Updated Date", "Acknowledged Date"
    ]
    for col in required:
        if col not in df.columns:
            df[col] = ""
    return df

from wpr_agent.state.influx_store import InfluxStore  # type: ignore
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None

try:
    from influxdb_client_3 import InfluxDBClient3  # type: ignore
except ImportError:
    InfluxDBClient3 = None


def to_point(row: Dict[str, Any], *, batch_id: str, source_filename: str, file_hash: str) -> Dict[str, Any]:
    bp_id = str(row.get("BP ID", "") or "")
    order_id = str(row.get("WP Order ID", "") or "")
    product = str(row.get("Product", "") or "")
    project_name = str(row.get("Project Name", "") or "")
    domain = str(row.get("Domain", "") or row.get("Domain1", "") or "")
    customer = str(row.get("Customer", "") or "")

    tags = {
        "product": product,
        "order_id": order_id,
        "bp_id": bp_id,
        "project_name": project_name,
        "domain": domain,
        "customer": customer,
        "batch_id": str(batch_id),
    }
    
    fields = {
        "source_filename": str(source_filename),
        "file_hash": str(file_hash),
    }
    
    # Add remaining fields as string fields for visibility
    for k, v in row.items():
        if k in ("Product", "WP Order ID", "BP ID", "Project Name", "Domain", "Domain1", "Customer"):
            continue
        if v is None:
            continue
        try:
            sval = str(v)
        except Exception:
            sval = ""
        fields[k.replace(" ", "_")] = sval
        
    return {
        "measurement": "wpr_input",
        "tags": tags,
        "fields": fields,
    }


def _resolve_latest_file(dir_path: Path, pattern: str) -> Optional[Path]:
    paths = sorted(dir_path.glob(pattern))
    if not paths:
        return None
    # pick latest by modified time
    latest: Tuple[float, Path] | None = None
    for p in paths:
        try:
            ts = p.stat().st_mtime
        except Exception:
            continue
        if latest is None or ts > latest[0]:
            latest = (ts, p)
    return latest[1] if latest else None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest_dataframe(df: pd.DataFrame, *, batch_id: Optional[str] = None, source_filename: str = "memory", file_hash: str = "memory") -> Dict[str, Any]:
    """Ingest a DataFrame directly to Influx wpr_input."""
    tracer = get_tracer()
    span = None
    try:
        if tracer:
            span = tracer.start_trace("ingest.dataframe", input={"rows": len(df), "batch_id": str(batch_id)})
    except Exception:
        span = None
    
    url = os.getenv("INFLUX_URL")
    token = os.getenv("INFLUX_TOKEN")
    org = os.getenv("INFLUX_ORG")
    bucket = os.getenv("INFLUX_BUCKET")
    if not (url and token and bucket):
        raise SystemExit("Missing INFLUX_URL/TOKEN/BUCKET in environment")

    if InfluxDBClient3 is None:
        raise SystemExit("influxdb-client-3 not installed")

    df = ensure_columns(df)
    if not batch_id:
        batch_id = datetime.now().strftime("%Y%m%d%H%M%S")

    store = InfluxStore()
    client = InfluxDBClient3(host=url, token=token, org=org, database=bucket)

    points: List[Any] = []
    for _, r in df.iterrows():
        row = {k: r.get(k, "") for k in df.columns}
        points.append(to_point(row, batch_id=str(batch_id), source_filename=source_filename, file_hash=file_hash))

    if points:
        # Batch writes
        batch_size = 2000
        for i in range(0, len(points), batch_size):
            chunk = points[i : i + batch_size]
            try:
                client.write(database=bucket, record=chunk, write_precision="s")
                time.sleep(0.1) 
            except Exception as e:
                print(f"write_warn: batch {i//batch_size} failed: {e}")
                time.sleep(5) 
                try:
                    client.write(database=bucket, record=chunk, write_precision="s")
                except Exception as e2:
                    print(f"write_error: batch {i//batch_size} failed retry: {e2}")
        
        # Verify write (SQL)
        try:
            query = f"SELECT count(*) FROM wpr_input WHERE batch_id = '{batch_id}'"
            table = client.query(query=query, language="sql")
            # InfluxDB 3 SQL count returns a column named 'count' or similar?
            # Actually, `count(*)` usually returns a column named `count_star` or similar in Arrow.
            # Let's just print the result for now or assume it worked if no error.
            # Or use `len(table.to_pylist())`? No, count returns 1 row with the count.
            rows = table.to_pylist()
            c = 0
            if rows:
                # Depending on backend, key might vary. Just grab first value.
                c = list(rows[0].values())[0]
            
            print(f"verify: wpr_input rows for batch_id={batch_id}: {c}")
        except Exception as _ver_ex:
            print(f"verify_warn: failed to count written points: {_ver_ex}")

    # Record summary
    store.register_ingestion_run(str(batch_id), file_hash, source_filename, len(points))
    try:
        if span:
            span.set_attribute("ok", True)
            span.end()
    except Exception:
        pass
    return {"ok": True, "rows": len(points), "batch_id": str(batch_id), "file": source_filename, "file_hash": file_hash}


def ingest_file(file_path: Path, *, sheet: str = "Sheet1", batch_id: Optional[str] = None, skip_dup: bool = True) -> Dict[str, Any]:
    """Ingest one Excel file to Influx wpr_input and record an ingestion_run summary."""
    tracer = get_tracer()
    span = None
    try:
        if tracer:
            span = tracer.start_trace("ingest.excel", input={"file": str(file_path), "sheet": sheet})
    except Exception:
        span = None
    url = os.getenv("INFLUX_URL")
    token = os.getenv("INFLUX_TOKEN")
    org = os.getenv("INFLUX_ORG")
    bucket = os.getenv("INFLUX_BUCKET")
    if not (url and token and bucket):
        raise SystemExit("Missing INFLUX_URL/TOKEN/BUCKET in environment")

    if InfluxDBClient3 is None:
        raise SystemExit("influxdb-client-3 not installed")

    # Read and normalize Excel
    df = pd.read_excel(str(file_path), sheet_name=sheet, engine="openpyxl").fillna("")
    df = ensure_columns(df)

    # Compute file hash and batch id
    file_hash = _sha256_file(file_path)
    if not batch_id:
        batch_id = datetime.now().strftime("%Y%m%d%H%M%S")

    store = InfluxStore()
    client = InfluxDBClient3(host=url, token=token, org=org, database=bucket)

    points: List[Any] = []
    for _, r in df.iterrows():
        row = {k: r.get(k, "") for k in df.columns}
        points.append(to_point(row, batch_id=str(batch_id), source_filename=str(file_path.name), file_hash=file_hash))

    if points:
        # Batch writes
        batch_size = 200
        for i in range(0, len(points), batch_size):
            chunk = points[i : i + batch_size]
            try:
                client.write(database=bucket, record=chunk, write_precision="s")
                time.sleep(1.0) # Pace out writes
            except Exception as e:
                print(f"write_warn: batch {i//batch_size} failed: {e}")
                time.sleep(10) # Backoff longer
                try:
                    client.write(database=bucket, record=chunk, write_precision="s")
                except Exception as e2:
                    print(f"write_error: batch {i//batch_size} failed retry: {e2}")
        
        # Verify write (SQL)
        try:
            query = f"SELECT count(*) FROM wpr_input WHERE batch_id = '{batch_id}'"
            table = client.query(query=query, language="sql")
            rows = table.to_pylist()
            c = 0
            if rows:
                c = list(rows[0].values())[0]
            print(f"verify: wpr_input rows for batch_id={batch_id}: {c}")
            try:
                if span:
                    span.set_attribute("rows", int(c))
            except Exception:
                pass
        except Exception as _ver_ex:
            print(f"verify_warn: failed to count written points: {_ver_ex}")

    # Record summary
    store.register_ingestion_run(str(batch_id), file_hash, str(file_path.name), len(points))
    try:
        if span:
            span.set_attribute("ok", True)
            span.set_attribute("batch_id", str(batch_id))
            span.end()
    except Exception:
        pass
    return {"ok": True, "rows": len(points), "batch_id": str(batch_id), "file": str(file_path), "file_hash": file_hash}


def main() -> None:
    ap = argparse.ArgumentParser(description="Upload Excel rows to Influx bucket")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", "-f")
    src.add_argument("--dir")
    ap.add_argument("--pattern", default="work_packages*.xlsx")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--batch-id")
    args = ap.parse_args()

    if args.file:
        p = Path(args.file)
        if not p.exists():
            raise SystemExit(f"File not found: {p}")
        res = ingest_file(p, sheet=args.sheet, batch_id=args.batch_id)
        if res.get("skipped"):
            print(f"skip: duplicate file {res.get('file')} ({res.get('file_hash')})")
        else:
            print(f"ok: uploaded {int(res.get('rows',0))} rows to wpr_input (batch_id={res.get('batch_id')})")
        return

    # Resolve latest in directory
    d = Path(args.dir)
    if not d.exists() or not d.is_dir():
        raise SystemExit(f"Directory not found: {d}")
    latest = _resolve_latest_file(d, args.pattern)
    if latest is None:
        raise SystemExit(f"No files match pattern '{args.pattern}' in {d}")
    res = ingest_file(latest, sheet=args.sheet, batch_id=args.batch_id)
    if res.get("skipped"):
        print(f"skip: duplicate file {res.get('file')} ({res.get('file_hash')})")
    else:
        print(f"ok: uploaded {int(res.get('rows',0))} rows to wpr_input (batch_id={res.get('batch_id')})")


if __name__ == "__main__":
    main()
