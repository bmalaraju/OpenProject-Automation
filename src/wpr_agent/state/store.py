from __future__ import annotations

from typing import Optional, Protocol


class StateStore(Protocol):
    def resolve_epic(self, project_key: str, order_id: str) -> Optional[str]:
        ...

    def register_epic(self, project_key: str, order_id: str, issue_key: str) -> None:
        ...

    def resolve_story(self, project_key: str, order_id: str, instance: int) -> Optional[str]:
        ...

    def register_story(self, project_key: str, order_id: str, instance: int, issue_key: str) -> None:
        ...

