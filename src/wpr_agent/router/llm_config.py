from __future__ import annotations

"""
LLM configuration (Phase 3) for Step 11 Router.

Provides a guarded LangChain Chat client at temperature=0. If unavailable or disabled,
returns None so tools can fall back to deterministic templates/rules.
"""

from typing import Any, Optional
import os
try:
    from wpr_agent.observability.langchain_integration import get_langchain_callbacks  # type: ignore
except Exception:  # pragma: no cover
    def get_langchain_callbacks():  # type: ignore
        return []


def get_llm_client(
    enabled: bool,
    *,
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    max_tokens: int = 300,
    timeout_s: int = 10,
) -> Optional[Any]:
    """Return a LangChain Chat model (temperature=0) or None if disabled/unavailable.

    Inputs
    - enabled: if False, always returns None
    - model/temperature/max_tokens/timeout_s: LLM params (temperature fixed to 0)

    Returns
    - Chat model instance supporting `.invoke()` or None when not available

    Notes
    - This function is import‑safe: it lazily imports LangChain and returns None if not present.
    - Tools MUST treat None as "fallback to deterministic behavior".
    """
    if not enabled:
        return None
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        # Prefer langchain_openai package
        from langchain_openai import ChatOpenAI  # type: ignore
        callbacks = get_langchain_callbacks()
        return ChatOpenAI(
            model=model,
            temperature=0.0,
            max_tokens=max_tokens,
            timeout=timeout_s,
            callbacks=callbacks if callbacks else None,
        )
    except Exception:
        # Fallback path: try legacy import or disable
        try:
            from langchain.chat_models import ChatOpenAI  # type: ignore
            callbacks = get_langchain_callbacks()
            return ChatOpenAI(
                model_name=model,
                temperature=0.0,
                max_tokens=max_tokens,
                request_timeout=timeout_s,
                callbacks=callbacks if callbacks else None,
            )
        except Exception:
            return None

