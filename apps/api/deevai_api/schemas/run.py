"""Run + Decision request/response shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RunRead(BaseModel):
    id: str
    line_item_id: str
    week_label: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    blended_cpv_target: Optional[float] = None
    blended_cpv_observed: Optional[float] = None
    blended_visits: Optional[int] = None
    blended_spend: Optional[float] = None
    n_decisions: int = 0
    n_changes_proposed: int = 0
    n_changes_applied: int = 0
    digest_text: Optional[str] = None
    digest_generated_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunTriggerRequest(BaseModel):
    line_item_id: str
    language: str = "it"


class DecisionRead(BaseModel):
    id: str
    run_id: str
    targeting_module: str
    targeting_key: str
    value: str
    field_label: Optional[str] = None
    previous_modifier: float
    new_modifier: float
    reason: str
    note: Optional[str] = None
    observed_impressions: Optional[int] = None
    observed_clicks: Optional[int] = None
    observed_visits: Optional[int] = None
    observed_cpv: Optional[float] = None
    status: str

    model_config = {"from_attributes": True}


class DecisionUpdateRequest(BaseModel):
    """Approve / reject a decision."""
    status: str  # "approved" | "rejected"


class RunApplyRequest(BaseModel):
    """Push approved decisions to Amazon DSP (honours DSP_DRY_RUN)."""
    force: bool = False
