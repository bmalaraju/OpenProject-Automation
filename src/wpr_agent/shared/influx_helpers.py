from __future__ import annotations

"""
Shared Influx helpers wrapping existing InfluxStore and ingestion utilities.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os

from wpr_agent.shared.config_loader import InfluxConfig


def ingest_excel_to_influx(file_path: Path, *, sheet: str = "Sheet1", batch_id: Optional[str] = None) -> Dict[str, Any]:
    """Delegate to the existing upload_excel_to_influx.ingest_file helper."""
    from wpr_agent.cli.upload_excel_to_influx import ingest_file  # type: ignore

    return ingest_file(file_path, sheet=sheet, batch_id=batch_id)


def query_wpr_rows(since: Optional[str] = None, batch_id: Optional[str] = None, measurement: str = "wpr_input") -> Any:
    """Return a DataFrame of rows from Influx using the router's normalized reader."""
    from wpr_agent.router.tools.influx_source import read_influx_df_tool  # type: ignore

    return read_influx_df_tool(since=since, batch_id=batch_id, measurement=measurement)


def get_order_checkpoint(project_key: str, order_id: str) -> Optional[str]:
    from wpr_agent.state.influx_store import InfluxStore  # type: ignore

    cfg = InfluxConfig.load()
    store = InfluxStore(url=cfg.url, token=cfg.token, org=cfg.org, bucket=cfg.bucket)
    return store.get_last_processed_time(project_key, order_id)


def set_order_checkpoint(project_key: str, order_id: str, last_ts_rfc3339: str) -> None:
    from wpr_agent.state.influx_store import InfluxStore  # type: ignore

    cfg = InfluxConfig.load()
    store = InfluxStore(url=cfg.url, token=cfg.token, org=cfg.org, bucket=cfg.bucket)
    store.set_last_processed_time(project_key, order_id, last_ts_rfc3339)


def get_source_hash(project_key: str, order_id: str) -> Optional[str]:
    from wpr_agent.state.influx_store import InfluxStore  # type: ignore

    cfg = InfluxConfig.load()
    store = InfluxStore(url=cfg.url, token=cfg.token, org=cfg.org, bucket=cfg.bucket)
    return store.get_source_hash(project_key, order_id)


def set_source_hash(project_key: str, order_id: str, src_hash: str) -> None:
    from wpr_agent.state.influx_store import InfluxStore  # type: ignore

    cfg = InfluxConfig.load()
    store = InfluxStore(url=cfg.url, token=cfg.token, org=cfg.org, bucket=cfg.bucket)
    store.set_source_hash(project_key, order_id, src_hash)


def compute_order_src_hash(product: str, sub_df: Any) -> str:
    """Use the existing hash logic on a grouped sub-dataframe."""
    from wpr_agent.router.tools.influx_source import compute_order_src_hash as _hash  # type: ignore

    return _hash(product, sub_df)


def get_last_row_time(product: str, order_id: str, *, since: Optional[str] = None, batch_id: Optional[str] = None) -> Optional[str]:
    """Wrap InfluxStore.get_last_row_time for convenience."""
    from wpr_agent.state.influx_store import InfluxStore  # type: ignore

    cfg = InfluxConfig.load()
    store = InfluxStore(url=cfg.url, token=cfg.token, org=cfg.org, bucket=cfg.bucket)
    return store.get_last_row_time(product, order_id, since=since, batch_id=batch_id)


def resolve_identity(project_key: str, order_id: str, issue_type: str = "Epic", instance: Optional[int] = None) -> Optional[str]:
    """Resolve an existing OpenProject issue key for a given WPR order."""
    from wpr_agent.state.influx_store import InfluxStore  # type: ignore

    cfg = InfluxConfig.load()
    store = InfluxStore(url=cfg.url, token=cfg.token, org=cfg.org, bucket=cfg.bucket)
    if issue_type.lower() == "story":
        return store.resolve_story(project_key, order_id, instance if instance is not None else 1)
    return store.resolve_epic(project_key, order_id)


def register_identity(
    project_key: str, order_id: str, issue_key: str, issue_type: str = "Epic", instance: Optional[int] = None, last_hash: Optional[str] = None
) -> None:
    """Register a new OpenProject issue key for a WPR order."""
    from wpr_agent.state.influx_store import InfluxStore  # type: ignore

    cfg = InfluxConfig.load()
    store = InfluxStore(url=cfg.url, token=cfg.token, org=cfg.org, bucket=cfg.bucket)
    if issue_type.lower() == "story":
        store.register_story(project_key, order_id, instance if instance is not None else 1, issue_key, last_hash)
    else:
        store.register_epic(project_key, order_id, issue_key, last_hash)
