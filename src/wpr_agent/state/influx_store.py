from __future__ import annotations

from typing import Optional, Dict, Any
import os
import time
import datetime

try:
    from influxdb_client_3 import InfluxDBClient3  # type: ignore
except ImportError:  # pragma: no cover
    InfluxDBClient3 = None  # type: ignore


class InfluxStore:
    """InfluxDB-backed state store for identity resolution (InfluxDB 3 / SQL).

    Measurement: issue_map
    Tags: project_key, issue_type ('Epic'|'Story'), order_id, instance (string or omitted for Epic)
    Fields: issue_key (string), last_hash (string, optional)

    Additional measurements supported by this store:
    - wpr_src_fp: per-order source fingerprint (idempotency input)
        Tags: project_key, order_id
        Fields: src_hash (string)
    - ingestion_run: per-file ingestion summary
        Tags: batch_id
        Fields: file_hash (string), source_filename (string), rows (int)
    - order_checkpoint: per-order last processed timestamp
        Tags: project_key, order_id
        Fields: last_ts (RFC3339 string)
    """

    def __init__(self, url: Optional[str] = None, token: Optional[str] = None, org: Optional[str] = None, bucket: Optional[str] = None) -> None:
        if InfluxDBClient3 is None:
            raise RuntimeError("influxdb-client-3 is not installed. pip install influxdb-client-3")
        self.url = url or os.getenv("INFLUX_URL") or ""
        self.token = token or os.getenv("INFLUX_TOKEN") or ""
        self.org = org or os.getenv("INFLUX_ORG") or ""
        self.bucket = bucket or os.getenv("INFLUX_BUCKET") or "wpr-state"
        if not (self.url and self.token and self.bucket):
            raise RuntimeError("InfluxStore requires INFLUX_URL, INFLUX_TOKEN, INFLUX_BUCKET")
        
        # Initialize InfluxDB 3 Client
        self.client = InfluxDBClient3(host=self.url, token=self.token, org=self.org, database=self.bucket)

    # ---- internal helpers ----
    def _query_sql(self, query: str) -> list[dict]:
        try:
            table = self.client.query(query=query, language="sql")
            return table.to_pylist()
        except Exception:
            return []

    def _last_issue_key(self, project_key: str, issue_type: str, order_id: str, instance: Optional[int]) -> Optional[str]:
        # Query the latest point for this identity
        inst_filter = f"AND instance = '{int(instance)}'" if instance is not None else ""
        query = f"""
        SELECT issue_key 
        FROM issue_map 
        WHERE project_key = '{project_key}' 
          AND issue_type = '{issue_type}' 
          AND order_id = '{order_id}' 
          {inst_filter}
        ORDER BY time DESC 
        LIMIT 1
        """
        rows = self._query_sql(query)
        if rows:
            return str(rows[0].get("issue_key", ""))
        return None

    def _write_mapping(self, project_key: str, issue_type: str, order_id: str, instance: Optional[int], issue_key: str, last_hash: Optional[str] = None) -> None:
        tags = {
            "project_key": project_key,
            "issue_type": issue_type,
            "order_id": order_id,
        }
        if instance is not None:
            tags["instance"] = str(int(instance))
        
        fields = {"issue_key": str(issue_key)}
        if last_hash is not None:
            fields["last_hash"] = str(last_hash)
        
        point = {
            "measurement": "issue_map",
            "tags": tags,
            "fields": fields,
        }
        try:
            self.client.write(database=self.bucket, record=point, write_precision="s")
        except Exception:
            pass

    # ---- Epic ----
    def resolve_epic(self, project_key: str, order_id: str) -> Optional[str]:
        return self._last_issue_key(project_key, "Epic", order_id, None)

    def register_epic(self, project_key: str, order_id: str, issue_key: str, last_hash: Optional[str] = None) -> None:
        self._write_mapping(project_key, "Epic", order_id, None, issue_key, last_hash)

    # ---- Story ----
    def resolve_story(self, project_key: str, order_id: str, instance: int) -> Optional[str]:
        return self._last_issue_key(project_key, "Story", order_id, int(instance))

    def register_story(self, project_key: str, order_id: str, instance: int, issue_key: str, last_hash: Optional[str] = None) -> None:
        self._write_mapping(project_key, "Story", order_id, int(instance), issue_key, last_hash)

    # ---- Last applied fingerprint ----
    def get_last_hash(self, project_key: str, issue_type: str, order_id: str, instance: Optional[int]) -> Optional[str]:
        inst_filter = f"AND instance = '{int(instance)}'" if instance is not None else ""
        query = f"""
        SELECT last_hash 
        FROM issue_map 
        WHERE project_key = '{project_key}' 
          AND issue_type = '{issue_type}' 
          AND order_id = '{order_id}' 
          {inst_filter}
        ORDER BY time DESC 
        LIMIT 1
        """
        rows = self._query_sql(query)
        if rows:
            val = rows[0].get("last_hash")
            return str(val) if val else None
        return None

    # ---- Source fingerprint (per order) ----
    def get_source_hash(self, project_key: str, order_id: str) -> Optional[str]:
        query = f"""
        SELECT src_hash 
        FROM wpr_src_fp 
        WHERE project_key = '{project_key}' 
          AND order_id = '{order_id}' 
        ORDER BY time DESC 
        LIMIT 1
        """
        rows = self._query_sql(query)
        if rows:
            val = rows[0].get("src_hash")
            return str(val) if val else None
        return None

    def set_source_hash(self, project_key: str, order_id: str, src_hash: str) -> None:
        try:
            point = {
                "measurement": "wpr_src_fp",
                "tags": {"project_key": str(project_key), "order_id": str(order_id)},
                "fields": {"src_hash": str(src_hash)},
            }
            self.client.write(database=self.bucket, record=point, write_precision="s")
        except Exception:
            pass

    # ---- Ingestion runs ----
    def has_ingestion_for_file(self, file_hash: str) -> bool:
        query = f"""
        SELECT file_hash 
        FROM ingestion_run 
        WHERE file_hash = '{file_hash}' 
          AND time >= now() - interval '90 days'
        LIMIT 1
        """
        rows = self._query_sql(query)
        return len(rows) > 0

    def register_ingestion_run(self, batch_id: str, file_hash: str, source_filename: str, rows: int) -> None:
        try:
            point = {
                "measurement": "ingestion_run",
                "tags": {"batch_id": str(batch_id)},
                "fields": {
                    "file_hash": str(file_hash),
                    "source_filename": str(source_filename),
                    "rows": int(rows)
                },
            }
            self.client.write(database=self.bucket, record=point, write_precision="s")
        except Exception:
            pass

    # ---- Order last data timestamp (from input measurement) ----
    def get_last_row_time(self, product: str, order_id: str, *, since: str | None = None, batch_id: str | None = None, measurement: str = "wpr_input") -> Optional[str]:
        """Return RFC3339 timestamp string of the latest point for (product, order_id)."""
        
        filters = [f"Product = '{product}'", f"\"WP Order ID\" = '{order_id}'"]
        # Note: InfluxDB 3 SQL uses double quotes for column names with spaces
        # But wait, the ingestion writes tags as "product" (lowercase) or "Product" (Title)?
        # In `influx_source.py` (v2), we mapped them.
        # In `upload_excel_to_influx.py`, we write columns as fields.
        # We need to be careful about column names.
        # Assuming the new ingestion writes "Product" and "WP Order ID" as columns.
        
        if batch_id:
            filters.append(f"batch_id = '{batch_id}'")
        
        where_clause = " AND ".join(filters)
        
        # Determine time range
        # SQL in InfluxDB 3 supports `time >= now() - interval 'X'`
        # `since` format: "365d" -> interval '365 days'
        interval = "365 days"
        if since:
            if since.endswith("d"):
                interval = f"{since[:-1]} days"
            elif since.endswith("h"):
                interval = f"{since[:-1]} hours"
        
        query = f"""
        SELECT time 
        FROM "{measurement}" 
        WHERE {where_clause} 
          AND time >= now() - interval '{interval}'
        ORDER BY time DESC 
        LIMIT 1
        """
        
        rows = self._query_sql(query)
        if rows:
            t = rows[0].get("time")
            if t:
                # Convert to ISO format if it's a datetime object
                if hasattr(t, "isoformat"):
                    return t.isoformat().replace("+00:00", "Z")
                return str(t)
        return None

    # ---- Per-order processed checkpoint ----
    def get_last_processed_time(self, project_key: str, order_id: str) -> Optional[str]:
        query = f"""
        SELECT last_ts 
        FROM order_checkpoint 
        WHERE project_key = '{project_key}' 
          AND order_id = '{order_id}' 
        ORDER BY time DESC 
        LIMIT 1
        """
        rows = self._query_sql(query)
        if rows:
            val = rows[0].get("last_ts")
            return str(val) if val else None
        return None

    def set_last_processed_time(self, project_key: str, order_id: str, last_ts_rfc3339: str) -> None:
        try:
            point = {
                "measurement": "order_checkpoint",
                "tags": {"project_key": str(project_key), "order_id": str(order_id)},
                "fields": {"last_ts": str(last_ts_rfc3339)},
            }
            self.client.write(database=self.bucket, record=point, write_precision="s")
        except Exception:
            pass

    # ---- Batch Optimization ----
    def get_all_checkpoints(self, project_key: str) -> dict[str, str]:
        """Fetch all last_processed_time timestamps for a project in one query."""
        query = f"""
        SELECT order_id, last_ts, time 
        FROM order_checkpoint 
        WHERE project_key = '{project_key}' 
          AND time >= now() - interval '365 days'
        ORDER BY time DESC
        """
        # Note: We fetch all and dedup in Python because SQL GROUP BY + LAST is complex to map to dict
        rows = self._query_sql(query)
        
        result = {}
        # Iterate in reverse order (oldest to newest) so newest overwrites? 
        # No, query is ORDER BY time DESC (newest first).
        # So we set if not exists.
        for row in rows:
            oid = row.get("order_id")
            val = row.get("last_ts")
            if oid and val and oid not in result:
                result[str(oid)] = str(val)
        return result

    def get_all_row_times(self, product: str, since: Optional[str] = None, batch_id: Optional[str] = None, measurement: str = "wpr_input") -> dict[str, str]:
        """Fetch all last row timestamps for a product in one query."""
        filters = [f"Product = '{product}'"]
        if batch_id:
            filters.append(f"batch_id = '{batch_id}'")
        
        where_clause = " AND ".join(filters)
        
        interval = "365 days"
        if since:
            if since.endswith("d"):
                interval = f"{since[:-1]} days"
            elif since.endswith("h"):
                interval = f"{since[:-1]} hours"
        
        # We need order_id (column "WP Order ID") and time
        query = f"""
        SELECT "WP Order ID" as order_id, time 
        FROM "{measurement}" 
        WHERE {where_clause} 
          AND time >= now() - interval '{interval}'
        ORDER BY time DESC
        """
        
        rows = self._query_sql(query)
        
        result = {}
        for row in rows:
            oid = row.get("order_id")
            t = row.get("time")
            if oid and t and oid not in result:
                if hasattr(t, "isoformat"):
                    result[str(oid)] = t.isoformat().replace("+00:00", "Z")
                else:
                    result[str(oid)] = str(t)
        return result

    # ---- Raw Excel row ingestion ----
    def write_wpr_row(self, project_key: str, order_id: str, wp_id: str, row: dict) -> None:
        """Write a single Excel row to measurement 'wpr_rows'."""
        try:
            tags = {
                "project_key": str(project_key),
                "order_id": str(order_id),
                "wp_id": str(wp_id)
            }
            fields = {}
            for k, v in (row or {}).items():
                fields[str(k)] = "" if v is None else str(v)
            
            point = {
                "measurement": "wpr_rows",
                "tags": tags,
                "fields": fields,
            }
            self.client.write(database=self.bucket, record=point, write_precision="s")
        except Exception:
            pass
