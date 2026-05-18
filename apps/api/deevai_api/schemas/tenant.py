"""Tenant request/response shapes."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")


class TenantRead(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
