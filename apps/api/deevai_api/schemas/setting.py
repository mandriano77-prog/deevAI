"""Tenant settings — optimizer + hygiene parameters."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .base import ApiModel

LineItemMode = Literal["observation_only", "approval_required", "auto_apply"]
DigestLanguage = Literal["it", "en"]

MAX_STEP_PER_RUN_CAP = 0.30


class SettingRead(ApiModel):
    id: str
    tenant_id: str
    default_cpv_target: float
    tolerance_band: float
    max_step_per_run: float
    max_modifier: float
    min_modifier_active: float
    exploration_revive_after_runs: int
    exploration_revive_modifier: float
    min_impressions_for_action: int
    min_visits_for_strong_action: int
    anomalous_ctr_threshold: float
    min_viewability: float
    observation_only_until: datetime | None
    default_line_item_mode: LineItemMode
    digest_language: DigestLanguage
    digest_delivery_email: bool

class SettingUpdate(ApiModel):
    default_cpv_target: float | None = Field(default=None, gt=0, le=5)
    tolerance_band: float | None = Field(default=None, gt=0, le=0.5)
    max_step_per_run: float | None = Field(default=None, gt=0, le=MAX_STEP_PER_RUN_CAP)
    max_modifier: float | None = Field(default=None, ge=1, le=5)
    min_modifier_active: float | None = Field(default=None, ge=0, le=1)
    exploration_revive_after_runs: int | None = Field(default=None, ge=1, le=12)
    exploration_revive_modifier: float | None = Field(default=None, ge=0.1, le=1)
    min_impressions_for_action: int | None = Field(default=None, ge=100, le=10_000)
    min_visits_for_strong_action: int | None = Field(default=None, ge=1, le=100)
    anomalous_ctr_threshold: float | None = Field(default=None, gt=0, le=0.2)
    min_viewability: float | None = Field(default=None, ge=0, le=1)
    default_line_item_mode: LineItemMode | None = None
    digest_language: DigestLanguage | None = None
    digest_delivery_email: bool | None = None

    @field_validator("max_step_per_run")
    @classmethod
    def cap_max_step(cls, v: float | None) -> float | None:
        if v is not None and v > MAX_STEP_PER_RUN_CAP:
            raise ValueError(f"max_step_per_run cannot exceed {MAX_STEP_PER_RUN_CAP}")
        return v
