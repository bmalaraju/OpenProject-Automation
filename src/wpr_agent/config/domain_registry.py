from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def normalize_domain(name: str) -> str:
    s = (name or "").strip().upper()
    # Replace non-alphanumeric with underscore, collapse repeats
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


def load_registry(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    reg = data.get("registry") or {}
    # Ensure keys are normalized
    return {normalize_domain(k): str(v or "").strip() for k, v in reg.items()}

