"""Reporting DTOs — read-only shapes for the dashboard.

Pydantic v2, camelCase JSON via the shared ``ApiModel`` base.

These models are **provider-agnostic**: they speak in terms of
``terms``, ``spend``, ``impressions``, ``clicks``, ``conversions`` —
never DSP-specific identifiers. That keeps the FE contract stable
when Engine B (Google DV360) lands."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field

from .base import ApiModel


# ---------------------------------------------------------------- KPIs


class RunKpiBlock(ApiModel):
    """Top-line KPIs for a run.

    All metric fields are optional: a run mid-flight, or a tenant with
    no impression delivery yet, simply leaves them ``None``."""

    spend: Optional[float] = Field(
        default=None, description="Total spend in advertiser currency.",
    )
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    conversions: Optional[int] = Field(
        default=None,
        description=(
            "Visit / lead events counted as the conversion signal for "
            "this line item. Maps to Run.blended_visits in v1."
        ),
    )

    # Derived rates (computed server-side so the FE doesn't have to)
    ctr: Optional[float] = Field(
        default=None, description="clicks / impressions; null if no impressions.",
    )
    cpm: Optional[float] = Field(
        default=None, description="1000 * spend / impressions; null if no impressions.",
    )
    cpa: Optional[float] = Field(
        default=None, description="spend / conversions; null if no conversions.",
    )
    roas: Optional[float] = Field(
        default=None,
        description=(
            "Return-on-ad-spend (Σ action value / spend). Pulled from "
            "Run.blended_roas; null when the funnel has no priced actions."
        ),
    )

    # Optional CPV (Engine A specific — we keep it for parity with the
    # existing schema but the FE can ignore it for non-CPV-targeted runs).
    cpv_target: Optional[float] = None
    cpv_observed: Optional[float] = None


class DecisionDistribution(ApiModel):
    """Counts describing what the engine did with the terms."""

    n_terms_evaluated: int = 0
    n_terms_changed: int = 0
    n_terms_boosted: int = 0
    n_terms_cut: int = 0
    n_terms_zeroed: int = 0


class RunSummaryDTO(ApiModel):
    """The full reporting payload for a single run."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    run_id: str
    line_item_id: str
    week_label: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    window_start: datetime
    window_end: datetime

    kpis: RunKpiBlock
    distribution: DecisionDistribution

    digest_text: Optional[str] = None


# ------------------------------------------------------------- Movers


class MoverDTO(ApiModel):
    """One of the top movers — a Decision sorted by ``abs(delta)``."""

    decision_id: str
    targeting_module: str
    targeting_key: str
    value: str
    field_label: Optional[str] = None

    old_modifier: float = Field(
        ..., description="Modifier before the run (Decision.previous_modifier).",
    )
    new_modifier: float = Field(
        ..., description="Modifier proposed by the engine for this run.",
    )
    delta: float = Field(
        ..., description="new_modifier - old_modifier (signed).",
    )
    abs_delta: float = Field(
        ..., description="Absolute magnitude of the change, used for sort.",
    )

    reason: str
    note: Optional[str] = None
    status: str


# ----------------------------------------------------- Constraint hits


class ConstraintEventDTO(ApiModel):
    """One time a hard constraint forced the engine to deviate.

    Today we surface these by reading Decisions with
    ``reason == 'constraint_violated'``. The triggering metric, observed
    value, operator/threshold and violation policy are parsed out of
    the Decision.note field which the engine writes in a fixed shape::

        constraint_violated_<metric>: observed <value> <op> <threshold> (<policy>)
    """

    decision_id: str
    targeting_module: str
    targeting_key: str
    value: str
    field_label: Optional[str] = None

    old_modifier: float
    new_modifier: float

    # Parsed from Decision.note (best-effort; falls back to None when the
    # note doesn't match the engine's canonical shape).
    metric: Optional[str] = None
    observed: Optional[float] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    policy: Optional[str] = Field(
        default=None,
        description="freeze | throttle | kill | alert (parsed from the engine note).",
    )

    raw_note: Optional[str] = None
