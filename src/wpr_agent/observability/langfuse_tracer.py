from __future__ import annotations

"""
Langfuse tracer shim with a no-op fallback.

Usage
- Call get_tracer() once per process and reuse for spans.
- If LANGFUSE_ENABLED is not '1' or SDK/config missing, all methods are no-ops.

Design
- Fail-open: never raise; swallow SDK/network errors.
- Sampling: trace-level sampling via env; errors always sampled via higher rate.
- Redaction: only attributes allowed; payload/body strings should be masked at call-site.
"""

from typing import Any, Dict, Optional
import os
import random


class _NoopSpan:
    def __init__(self) -> None:
        self.ok = True

    def set_attribute(self, _key: str, _value: Any) -> None:  # noqa: D401
        return

    def end(self, **_kw: Any) -> None:
        return


class _NoopTracer:
    def start_trace(self, *_args: Any, **_kw: Any) -> _NoopSpan:
        return _NoopSpan()

    def start_span(self, *_args: Any, **_kw: Any) -> _NoopSpan:
        return _NoopSpan()

    def record_error(self, *_args: Any, **_kw: Any) -> None:
        return


_CACHED: Optional[Any] = None


def get_tracer() -> Any:
    """Return a tracer that matches the minimal interface used by the app.

    When disabled or misconfigured, returns a no-op tracer.
    """
    global _CACHED
    if _CACHED is not None:
        return _CACHED
    try:
        if str(os.getenv("LANGFUSE_ENABLED", "0")).strip() != "1":
            _CACHED = _NoopTracer()
            return _CACHED
        host = os.getenv("LANGFUSE_HOST")
        pub = os.getenv("LANGFUSE_PUBLIC_KEY")
        sec = os.getenv("LANGFUSE_SECRET_KEY")
        if not (host and pub and sec):
            _CACHED = _NoopTracer()
            return _CACHED
        try:
            from langfuse import Langfuse  # type: ignore
        except Exception:
            _CACHED = _NoopTracer()
            return _CACHED

        client = Langfuse(
            host=host,
            public_key=pub,
            secret_key=sec,
        )

        class _Tracer:
            def __init__(self, _client: Any) -> None:
                self.client = _client
                try:
                    self.sample_rate = float(os.getenv("LANGFUSE_SAMPLE_RATE", "0.25"))
                except Exception:
                    self.sample_rate = 0.25
                try:
                    self.error_sample_rate = float(os.getenv("LANGFUSE_ERROR_SAMPLE_RATE", "1.0"))
                except Exception:
                    self.error_sample_rate = 1.0

            def _sampled(self, is_error: bool = False) -> bool:
                rate = self.error_sample_rate if is_error else self.sample_rate
                if rate >= 1.0:
                    return True
                if rate <= 0.0:
                    return False
                return random.random() < rate

            def start_trace(self, name: str, *, input: Optional[Dict[str, Any]] = None, **attrs: Any) -> Any:  # noqa: A002
                try:
                    if not self._sampled(False):
                        return _NoopSpan()
                    tr = self.client.trace(
                        name=name,
                        input=input or {},
                        **{"metadata": attrs},
                    )
                    return tr
                except Exception:
                    return _NoopSpan()

            def start_span(self, name: str, *, parent: Optional[Any] = None, **attrs: Any) -> Any:
                try:
                    if isinstance(parent, _NoopSpan):
                        return _NoopSpan()
                    # If parent is missing (e.g., trace not sampled), noop
                    if parent is None or getattr(parent, "id", None) is None:
                        return _NoopSpan()
                    sp = self.client.span(
                        name=name,
                        trace_id=getattr(parent, "id", None),
                        **{"metadata": attrs},
                    )
                    return sp
                except Exception:
                    return _NoopSpan()

            def record_error(self, parent: Optional[Any], error: Exception, **attrs: Any) -> None:
                try:
                    if not self._sampled(True):
                        return
                    md = {"type": error.__class__.__name__, "message": str(error)}
                    md.update(attrs or {})
                    # If parent exists, attach as event; else fire standalone trace
                    if parent is not None and getattr(parent, "id", None) is not None:
                        ev = self.client.event(
                            name="error",
                            trace_id=getattr(parent, "id", None),
                            **{"metadata": md},
                        )
                        try:
                            ev.end()
                        except Exception:
                            pass
                        return
                    tr = self.client.trace(name="error", input=md)
                    try:
                        tr.end()
                    except Exception:
                        pass
                except Exception:
                    return

        _CACHED = _Tracer(client)
        return _CACHED
    except Exception:
        _CACHED = _NoopTracer()
        return _CACHED

