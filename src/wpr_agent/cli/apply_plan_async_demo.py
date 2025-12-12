from __future__ import annotations

"""
Demo: async create a few Epics/Stories using the async OP client/service.
Not integrated into router; for Phase 2 validation only.
"""

import asyncio
from typing import Any, Dict

from dotenv import load_dotenv

from wpr_agent.services.openproject_service_async import OpenProjectServiceV2Async  # type: ignore


async def main() -> None:
    load_dotenv(".env", override=False)
    svc = OpenProjectServiceV2Async()
    project = "FlowOne"
    ok, body = await svc.create_issue(project, "Epic", {"summary": "Async Demo Epic", "description": "demo"})
    print("epic_create", ok, body)
    if not ok:
        return
    epic_key = str(body.get("key") or body.get("id") or "").strip()
    if not epic_key:
        return
    # Create 3 stories concurrently
    async def _mk(i: int):
        return await svc.create_issue(project, "Story", {"summary": f"Async Demo Story {i}", "parent": {"key": epic_key}})
    res = await asyncio.gather(*[_mk(i) for i in range(1, 4)], return_exceptions=True)
    print("stories", res)


if __name__ == "__main__":
    asyncio.run(main())

