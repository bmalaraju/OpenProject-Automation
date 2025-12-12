from __future__ import annotations

"""
Registry tools for Step 11 Router (Phase 2).

Tools
- load_registry_tool(path) -> dict[str,str]
  Load Domain→Project registry JSON and normalize domain keys.

- normalize_domain_tool(name) -> str
  Normalize a single domain string (uppercase; non‑alphanumerics→underscore; collapse repeats).
"""

from typing import Dict

from pathlib import Path
from wpr_agent.config.domain_registry import load_registry, normalize_domain
from wpr_agent.router.utils import log_kv


def load_registry_tool(path: str) -> Dict[str, str]:
    """Load Domain→Project registry and normalize domain keys.

    Inputs
    - path: str; JSON file containing { "registry": { raw_domain: project_key, ... } }

    Returns
    - dict[str,str]: normalized_domain → project_key

    Side effects
    - Logs entry count and a sample of keys
    """
    p = Path(path)
    reg = load_registry(path=p)
    log_kv("registry_load", entries=len(reg), path=path)
    # print sample keys, if any
    sample = list(reg.keys())[:3]
    log_kv("registry_normalized", sample_keys=sample)
    return reg


def normalize_domain_tool(name: str) -> str:
    """Normalize a domain string.

    Behavior
    - Trim whitespace; uppercase; replace non‑alphanumerics with underscores; collapse repeats; strip edges.
    - Mirrors normalize_domain() used across the codebase.
    """
    out = normalize_domain(name)
    log_kv("domain_normalize", raw=name, normalized=out)
    return out

def load_product_registry_tool(path: str) -> Dict[str, str]:
    """Load Product?Project registry JSON.

    Inputs
    - path: str; JSON file containing { "registry": { product: project_key, ... } }

    Returns
    - dict[str,str]: product ? project_key

    Side effects
    - Logs entry count and a sample of keys
    """
    p = Path(path)
    if not p.exists():
        log_kv("product_registry_load", entries=0, path=path, missing=True)
        return {}
    try:
        data = p.read_text(encoding="utf-8")
        import json as _json
        obj = _json.loads(data)
    except Exception:
        log_kv("product_registry_load", entries=0, path=path, error=True)
        return {}
    reg = obj.get("registry") or {}
    out = {str(k).strip(): str(v or "").strip() for k, v in reg.items()}
    log_kv("product_registry_load", entries=len(out), path=path, sample=list(out.keys())[:3])
    return out
