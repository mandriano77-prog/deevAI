"""Line item list shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LineItemRead(BaseModel):
    id: str
    advertiser_id: str
    name: str
    amazon_line_item_id: str
    amazon_ad_group_id: str | None = None
    amazon_bid_adjustment_rule_id: str | None = None
    cpv_target: float
    current_max_bid: float | None = None
    mode: str
    status: str

    model_config = {"from_attributes": True}


class LineItemCreate(BaseModel):
    advertiser_id: str
    name: str = Field(min_length=1, max_length=240)
    amazon_line_item_id: str = Field(min_length=1, max_length=80)
    amazon_ad_group_id: str | None = Field(default=None, max_length=80)
    cpv_target: float = Field(gt=0)
    current_max_bid: float | None = Field(default=None, gt=0)
    visit_event_id: str | None = Field(default=None, max_length=80)
    mode: str = Field(default="observation_only")


class LineItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    amazon_line_item_id: str | None = Field(default=None, max_length=80)
    amazon_ad_group_id: str | None = Field(default=None, max_length=80)
    amazon_bid_adjustment_rule_id: str | None = Field(default=None, max_length=36)
    cpv_target: float | None = Field(default=None, gt=0)
    current_max_bid: float | None = Field(default=None, gt=0)
    mode: str | None = None
    status: str | None = None
