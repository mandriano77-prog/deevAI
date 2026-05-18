"""Advertiser request/response shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdvertiserRead(BaseModel):
    id: str
    integration_id: str
    amazon_advertiser_id: str
    name: str
    currency: str
    country: str
    status: str

    model_config = {"from_attributes": True}


class AdvertiserCreate(BaseModel):
    integration_id: str
    amazon_advertiser_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    country: str = Field(default="IT", min_length=2, max_length=2)
