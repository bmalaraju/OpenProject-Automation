from __future__ import annotations

"""
Simple JSON-backed catalog for identity-based resolve-or-create.

This is a local fallback state store used to prevent duplicate Jira issue
creation when remote search is unreliable. In production, back this interface
with Postgres/TimescaleDB.

Keys
- Epic: (project_key, order_id)
- Story: (project_key, order_id, instance)

File layout example:
{
  "epics": {"NM::WPO001234": "NM-101"},
  "stories": {"NM::WPO001234::1": "NM-102"}
}
"""

from typing import Dict, Optional
import json
from pathlib import Path


class Catalog:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.epics: Dict[str, str] = {}
        self.stories: Dict[str, str] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.epics = dict(data.get("epics", {}))
                self.stories = dict(data.get("stories", {}))
            except Exception:
                self.epics = {}
                self.stories = {}
        self._loaded = True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"epics": self.epics, "stories": self.stories}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _ek(project_key: str, order_id: str) -> str:
        return f"{project_key}::{order_id}".strip()

    @staticmethod
    def _sk(project_key: str, order_id: str, instance: int) -> str:
        return f"{project_key}::{order_id}::{int(instance)}".strip()

    # --- Epic ---
    def resolve_epic(self, project_key: str, order_id: str) -> Optional[str]:
        self.load()
        return self.epics.get(self._ek(project_key, order_id))

    def register_epic(self, project_key: str, order_id: str, issue_key: str) -> None:
        self.load()
        self.epics[self._ek(project_key, order_id)] = issue_key

    # --- Story ---
    def resolve_story(self, project_key: str, order_id: str, instance: int) -> Optional[str]:
        self.load()
        return self.stories.get(self._sk(project_key, order_id, instance))

    def register_story(self, project_key: str, order_id: str, instance: int, issue_key: str) -> None:
        self.load()
        self.stories[self._sk(project_key, order_id, instance)] = issue_key

