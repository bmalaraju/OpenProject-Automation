from __future__ import annotations

from typing import List, Dict, Optional
from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    id: Optional[str] = None
    subject: str
    description: str = ""
    type: str = "Task"
    status: Optional[str] = None
    custom_fields: Dict[str, object] = Field(default_factory=dict)


class PlanPayload(BaseModel):
    project_key: str
    items: List[PlanItem]


class WprConfig(BaseModel):
    source: str = "influx"  # "excel" or "influx"
    file: Optional[str] = None
    sheet: str = "Sheet1"
    since: Optional[str] = None
    batch_id: Optional[str] = None
    project_key: str
    dry_run: bool = False

    @classmethod
    def from_env_or_kwargs(cls, **kwargs: object) -> "WprConfig":
        import os
        data = dict(kwargs)
        data.setdefault("file", os.getenv("WPR_EXCEL_FILE") or None)
        data.setdefault("sheet", os.getenv("WPR_EXCEL_SHEET") or "Sheet1")
        data.setdefault("since", os.getenv("WPR_SINCE") or None)
        data.setdefault("batch_id", os.getenv("WPR_BATCH_ID") or None)
        data.setdefault("project_key", os.getenv("WPR_PROJECT_KEY") or "")
        data.setdefault("dry_run", os.getenv("WPR_DRY_RUN", "0") == "1")
        if not data.get("project_key"):
            raise ValueError("project_key is required (env WPR_PROJECT_KEY or config)")
        return cls(**data)


class WprState(BaseModel):
    config: WprConfig
    rows: List[Dict[str, object]] = Field(default_factory=list)
    delta_orders: List[Dict[str, object]] = Field(default_factory=list)
    plan: Optional[PlanPayload] = None
    apply_result: Optional[Dict[str, object]] = None
    errors: List[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
