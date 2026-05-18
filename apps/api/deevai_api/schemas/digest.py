"""Digest request/response shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DigestGenerateRequest(BaseModel):
    """Generate a digest for a specific run.

    For Sprint 2.4 we accept either a `run_id` (looks up the Plan from DB)
    OR a synthetic mode where the FE passes the Plan inline (for the
    "regenerate from dashboard" button on mock data)."""

    run_id: str | None = None
    language: Literal["it", "en"] = "it"
    previous_week_cpv: float | None = None
    previous_week_visits: int | None = None


class DigestResponse(BaseModel):
    run_id: str | None = None
    week_label: str
    language: str
    text: str
    generated_at: datetime
    provider: str  # "anthropic" | "openai" | "template"
    cached: bool = False
