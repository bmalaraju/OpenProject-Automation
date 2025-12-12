"""
Router type contracts for Step 11 (Phase 1: Contracts & State).

Contains:
- RouterConfig: validated configuration for a router run
- AgentState: resumable state across Steps 7→8→9→10
- RouteDecision: lightweight record of which steps to run per domain/project

Notes
- This module is import‑only; it has no side effects beyond model validation.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

from wpr_agent.models import TrackerFieldMap, PlanBundle, ValidationReport


class RouterConfig(BaseModel):
    """Validated configuration for the Step 11 router.

    Inputs
    - file: Excel file path
    - sheet: Excel sheet name
    - registry_path: JSON file mapping Domain→Project
    - offline/online: mutually exclusive mode flags
    - dry_run: when true, compile+validate+report only (no apply)
    - continue_on_error: apply only passing orders (legacy: BPs) when validation fails
    - domains_filter: optional raw domain filter list
    - max_retries/backoff_base: resilience settings for Step 6
    - artifact_dir/report_path/summary_path: report destinations (optional)
    """
    # Product/Order route notes:
    # - grouped uses Product->[(Order ID, subdf)] (legacy Domain->[(BP ID, subdf)])
    # - apply_mask holds allowed order IDs (legacy: BP IDs)
    # - apply_progress tracks next order index (legacy: BP index)

    # Source selection: 'excel' or 'influx'
    source: str = "excel"

    # Excel inputs (when source == 'excel')
    file: str = ""
    sheet: str = "Sheet1"
    # Influx inputs (when source == 'influx')
    since: Optional[str] = None
    batch_id: Optional[str] = None
    delta_only: bool = False
    registry_path: str

    offline: bool = False
    online: bool = False
    dry_run: bool = False
    continue_on_error: bool = False
    domains_filter: List[str] = Field(default_factory=list)

    max_retries: int = 3
    backoff_base: float = 0.5

    artifact_dir: Optional[str] = None
    report_path: Optional[str] = None
    summary_path: Optional[str] = None
    # Optional: use async create-only path for OpenProject (Phase 2)
    async_create_only: bool = False

    @model_validator(mode="after")
    def _check_modes(self) -> "RouterConfig":
        if self.offline == self.online:
            raise ValueError("Exactly one of offline/online must be True.")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.backoff_base <= 0:
            raise ValueError("backoff_base must be > 0")
        # Validate source-specific requireds
        s = (self.source or "excel").strip().lower()
        if s not in ("excel", "influx"):
            raise ValueError("source must be 'excel' or 'influx'")
        if s == "excel":
            if not self.file:
                raise ValueError("file is required when source=excel")
        return self


class AgentState(BaseModel):
    """Serializable router state spanning compile→validate→apply→report.

    Fields
    - run_id: unique run identifier
    - mode: {offline, online, dry_run}
    - config: RouterConfig instance
    - registry: normalized domain→project_key mapping
    - excel_df: normalized DataFrame with ensured columns
    - grouped: Domain→[(BP ID, subdf)] groups for planning
    - fieldmaps: project_key→JiraFieldMap
    - bundles: compiled PlanBundle list (Step 7)
    - validation_reports: per project ValidationReport (Step 8)
    - apply_mask: project_key→allowed order IDs (legacy: BP IDs) (post‑validation policy)
    - domain_results: per‑domain apply aggregates for reporting
    - run_report: overall RunReport (dict) built in Step 10
    - errors/warnings: router‑level messages
    - llm_enabled: LLM can be called (opt‑in)
    """

    run_id: str
    mode: Dict[str, bool]
    config: RouterConfig

    registry: Dict[str, str] = Field(default_factory=dict)
    excel_df: Optional[pd.DataFrame] = None
    grouped: Optional[List[Tuple[str, List[Tuple[str, pd.DataFrame]]]]] = None
    fieldmaps: Dict[str, TrackerFieldMap] = Field(default_factory=dict)
    bundles: List[PlanBundle] = Field(default_factory=list)
    validation_reports: Dict[str, ValidationReport] = Field(default_factory=dict)
    apply_mask: Dict[str, Set[str]] = Field(default_factory=dict)
    domain_results: List[Dict] = Field(default_factory=list)
    run_report: Optional[Dict] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    llm_enabled: bool = False
    # Checkpoint/resume cursor: per-project next order index (legacy: BP index) to apply
    apply_progress: Dict[str, int] = Field(default_factory=dict)

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: Dict[str, bool]) -> Dict[str, bool]:
        keys = {"offline", "online", "dry_run"}
        if not keys.issubset(set(v.keys())):
            raise ValueError("mode must include offline, online, dry_run keys")
        if bool(v.get("offline")) == bool(v.get("online")):
            raise ValueError("mode.offline and mode.online must be mutually exclusive")
        return v

    model_config = {
        "arbitrary_types_allowed": True,
    }


class RouteDecision(BaseModel):
    """Record the routing choices for a domain/project pair."""

    compile: bool = False
    validate: bool = False
    apply: bool = False
    report: bool = True
    reasons: List[str] = Field(default_factory=list)




