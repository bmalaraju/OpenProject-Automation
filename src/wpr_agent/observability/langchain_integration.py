from __future__ import annotations

"""
Optional LangChain → Langfuse callback integration.

Enabled only when both LANGFUSE_ENABLED=1 and ROUTER_LLM_ENABLED=1.
Falls back to noop when dependencies/config are missing.
"""

from typing import Any, Optional
import os


def get_langchain_callbacks() -> list[Any]:
    try:
        if not (os.getenv("LANGFUSE_ENABLED") == "1" and os.getenv("ROUTER_LLM_ENABLED") == "1"):
            return []
        from langfuse.callback import CallbackHandler  # type: ignore
        handler = CallbackHandler(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", ""),
        )
        return [handler]
    except Exception:
        return []

