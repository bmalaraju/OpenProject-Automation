from __future__ import annotations

"""
Influx source tools: build a normalized DataFrame and compute per-order source fingerprints
for delta detection (InfluxDB 3 / SQL).

Tools
- read_influx_df_tool(since=None, batch_id=None) -> pandas.DataFrame
- group_product_order_from_df_tool(df) -> list[(product, [(order_id, subdf)])]
- compute_order_src_hash(product, subdf) -> str
"""

from typing import Any, List, Tuple, Optional
import os
import json
import hashlib

import pandas as pd
try:
    from wpr_agent.observability.langfuse_tracer import get_tracer  # type: ignore
except Exception:  # pragma: no cover
    def get_tracer():  # type: ignore
        return None


def _ensure_influx_client():
    try:
        import influxdb_client_3  # type: ignore
        return influxdb_client_3
    except Exception as ex:  # pragma: no cover
        raise RuntimeError(f"influxdb-client-3 not installed: {ex}")


def _bucket_env() -> Tuple[str, str, str, str]:
    url = os.getenv("INFLUX_URL") or ""
    token = os.getenv("INFLUX_TOKEN") or ""
    org = os.getenv("INFLUX_ORG") or ""
    bucket = os.getenv("INFLUX_BUCKET") or ""
    if not (url and token and bucket):
        raise RuntimeError("Missing INFLUX_URL/TOKEN/BUCKET in environment")
    return url, token, org, bucket


def read_influx_df_tool(since: Optional[str] = None, batch_id: Optional[str] = None, measurement: str = "wpr_input") -> pd.DataFrame:
    influxdb_client_3 = _ensure_influx_client()
    url, token, org, bucket = _bucket_env()
    
    client = influxdb_client_3.InfluxDBClient3(host=url, token=token, org=org, database=bucket)
    
    # Determine time range
    # SQL: time >= now() - interval 'X'
    interval = "7 days"
    if since:
        s = str(since).strip()
        if s.endswith("d"):
            interval = f"{s[:-1]} days"
        elif s.endswith("h"):
            interval = f"{s[:-1]} hours"
        elif s.isdigit():
             interval = f"{s} days" # Default to days if just number? Or assume hours? Let's assume days if not specified or just pass through if user knows what they are doing.
             # Actually, let's just be safe.
             pass

    filters = []
    if batch_id:
        filters.append(f"batch_id = '{batch_id}'")
    
    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)
        where_clause += f" AND time >= now() - interval '{interval}'"
    else:
        where_clause = f"WHERE time >= now() - interval '{interval}'"

    query = f"""
    SELECT * 
    FROM "{measurement}" 
    {where_clause}
    ORDER BY time ASC
    """
    
    if os.getenv("INFLUX_DEBUG") == "1":
        print(f"influx_debug: bucket={bucket} sql=\n{query}")

    tracer = get_tracer()
    span = None
    try:
        if tracer:
            span = tracer.start_trace(
                "influx.query",
                input={"range": interval, "measurement": measurement, "batch_id": batch_id or ""},
            )
    except Exception:
        span = None
    
    try:
        table = client.query(query=query, language="sql")
        df = table.to_pandas()
        
        if os.getenv("INFLUX_DEBUG") == "1":
            print(f"influx_read_primary: rows={len(df)}")
            
        if span:
            try:
                span.set_attribute("rows", len(df))
            except Exception:
                pass
            
    except Exception as e:
        if os.getenv("INFLUX_DEBUG") == "1":
            print(f"influx_read_error: {e}")
        if span:
            tracer.record_error(span, e)
        # Return empty DF on error
        # Return empty DF on error
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # InfluxDB 3 SQL returns columns as is.
    # We need to ensure tag columns are strings.
    tag_cols = ["product", "order_id", "bp_id", "project_name", "domain", "customer", "batch_id"]
    for c in tag_cols:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str)

    # Convert underscored field names back to spaced column names
    # In `upload_excel_to_influx.py`, we replaced spaces with underscores.
    rename_cols = {}
    for c in list(df.columns):
        if isinstance(c, str) and c not in tag_cols and c not in ("source_filename", "file_hash", "time") and "_" in c:
             # Heuristic: replace underscores with spaces if it looks like a field we normalized
             # But wait, some fields might naturally have underscores?
             # The normalization was `k.replace(" ", "_")`.
             # So we reverse it.
             rename_cols[c] = c.replace("_", " ")
    
    df = df.rename(columns=rename_cols)

    # Map tag columns to normalized Excel column names expected downstream
    tag_map = {
        "product": "Product",
        "order_id": "WP Order ID",
        "bp_id": "BP ID",
        "project_name": "Project Name",
        "domain": "Domain",
        "customer": "Customer",
    }
    for src, dst in tag_map.items():
        if src in df.columns:
            df[dst] = df[src]

    # Local implementation of ensure_columns (replacing missing wpr_agent.tools.excel_tools)
    def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
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

    norm = _ensure_columns(df.fillna(""))
    
    try:
        if span:
            span.set_attribute("rows_out", int(getattr(norm, 'shape', [0,0])[0]))
            span.end()
    except Exception:
        pass
    return norm


def group_product_order_from_df_tool(df: pd.DataFrame) -> List[Tuple[str, List[Tuple[str, pd.DataFrame]]]]:
    result: List[Tuple[str, List[Tuple[str, pd.DataFrame]]]] = []
    for prod_val, prod_df in df.groupby("Product", dropna=False):
        orders = [(str(oid or ""), sub) for oid, sub in prod_df.groupby("WP Order ID", dropna=False)]
        result.append((str(prod_val or ""), orders))
    return result


def compute_order_src_hash(product: str, sub: pd.DataFrame) -> str:
    # Use a subset of columns that feed compile/apply
    cols = [
        "WP Order ID",
        "WP Order Status",
        "WP ID",
        "WP Name",
        "WP Quantity",
        "Employee Name",
        "STD",
        "WP Requested Delivery Date",
        "WP Readiness Date",
        "PO StartDate",
        "PO EndDate",
        "Approved Date",
        "Submitted Date",
        "Cancelled Date",
        "Project Name",
        "Product",
        "Domain",
        "Customer",
    ]
    parts: List[Any] = [str(product or "")] 
    for c in cols:
        try:
            vals = list(sub[c])
        except Exception:
            vals = []
        parts.append({c: ["" if v is None else str(v) for v in vals]})
    s = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
