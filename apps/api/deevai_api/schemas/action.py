"""Pydantic schemas for Action CRUD and funnel configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ApiModel

ActionType = Literal["visit", "lead", "purchase", "engagement", "custom"]
ValueSource = Literal["static", "dynamic", "modeled"]
TrackingSource = Literal["pixel", "s2s_postback", "api", "manual_upload"]
DedupeRule = Literal["per_session", "per_user", "first_only", "every"]
ActionStatus = Literal["active", "paused", "archived"]


class ActionRead(ApiModel):
    id: str
    tenant_id: str
    line_item_id: str | None
    name: str
    type: ActionType
    weight: float
    value_eur: float
    value_source: ValueSource
    value_currency: str
    tracking_source: TrackingSource
    attribution_window_hours: int
    dedupe_rule: DedupeRule
    quality_filter: dict[str, Any] | None
    funnel_parent_id: str | None
    funnel_position: int | None
    status: ActionStatus

class ActionCreate(ApiModel):
    line_item_id: str | None = None
    name: str = Field(min_length=1, max_length=160)
    type: ActionType = "visit"
    weight: float = Field(default=1.0, gt=0)
    value_eur: float = Field(default=0.0, ge=0)
    value_source: ValueSource = "static"
    value_currency: str = Field(default="EUR", min_length=3, max_length=3)
    tracking_source: TrackingSource = "pixel"
    attribution_window_hours: int = Field(default=168, ge=1, le=24 * 30)
    dedupe_rule: DedupeRule = "per_session"
    quality_filter: dict[str, Any] | None = None
    funnel_parent_id: str | None = None
    funnel_position: int | None = Field(default=None, ge=1)
    status: ActionStatus = "active"


class ActionUpdate(ApiModel):
    line_item_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    type: ActionType | None = None
    weight: float | None = Field(default=None, gt=0)
    value_eur: float | None = Field(default=None, ge=0)
    value_source: ValueSource | None = None
    value_currency: str | None = Field(default=None, min_length=3, max_length=3)
    tracking_source: TrackingSource | None = None
    attribution_window_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    dedupe_rule: DedupeRule | None = None
    quality_filter: dict[str, Any] | None = None
    funnel_parent_id: str | None = None
    funnel_position: int | None = Field(default=None, ge=1)
    status: ActionStatus | None = None


class ActionFunnelSet(ApiModel):
    ordered_action_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> ActionFunnelSet:
        if len(self.ordered_action_ids) != len(set(self.ordered_action_ids)):
            raise ValueError("ordered_action_ids must be unique")
        return self
