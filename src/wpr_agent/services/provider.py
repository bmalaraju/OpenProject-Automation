from __future__ import annotations

import os
from typing import Any


def make_service() -> Any:
    """Factory returning the OpenProject service instance."""
    from wpr_agent.services.openproject_service_v2 import OpenProjectServiceV2  # type: ignore

    return OpenProjectServiceV2()

