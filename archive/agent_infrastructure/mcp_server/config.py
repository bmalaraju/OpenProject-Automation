from __future__ import annotations

import os
from typing import Literal, Optional, TypedDict


class McpConfig(TypedDict, total=False):
    transport: Literal["stdio", "ws"]
    cmd: Optional[str]
    url: Optional[str]
    timeout_sec: float
    fallback_local_on_error: bool


def is_enabled() -> bool:
    v = os.getenv("MCP_WPR_TRANSPORT", "").strip().lower()
    return v in {"stdio", "ws", "http", "https"}


def load() -> McpConfig:
    transport = os.getenv("MCP_WPR_TRANSPORT", "").strip().lower()
    cfg: McpConfig = {}
    if transport in {"stdio", "ws", "http", "https"}:
        cfg["transport"] = transport  # type: ignore[assignment]
    if transport == "stdio":
        cfg["cmd"] = os.getenv("MCP_WPR_CMD", "") or None
    if transport in {"ws", "http", "https"}:
        cfg["url"] = os.getenv("MCP_WPR_URL", "") or None
    try:
        cfg["timeout_sec"] = float(os.getenv("MCP_TIMEOUT_SEC", "30"))
    except Exception:
        cfg["timeout_sec"] = 30.0
    cfg["fallback_local_on_error"] = os.getenv("MCP_FALLBACK_LOCAL_ON_ERROR", "1") != "0"
    return cfg
