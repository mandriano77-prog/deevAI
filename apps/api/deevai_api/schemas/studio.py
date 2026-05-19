"""Studio DTOs — Custom Bidding script generation + simulation.

Pydantic v2, camelCase JSON via the shared :class:`ApiModel` base.

The "Studio" is the FE surface where a customer drives three sliders
(Performance / Quality / Reach), generates a deterministic DV360
Custom Bidding script, and simulates its score distribution against
a synthetic (or, later, real Floodlight) dataset.

All schemas are provider-agnostic: nothing here mentions DV360 or
Floodlight by name except as enum values. The same shapes will ship
to whatever DSP we add Engine B support for next.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field, model_validator

from .base import ApiModel


# --------------------------------------------------------------- weights


class ObjectiveWeightsDTO(ApiModel):
    """The three slider weights, each in [0..100], summing to exactly 100.

    Stored on the wire as integers (percent) — the FE works in whole
    points, so we never need fractional precision. The engine takes
    floats in [0..1]; conversion happens in the service layer.
    """

    performance: int = Field(ge=0, le=100)
    quality: int = Field(ge=0, le=100)
    reach: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _check_sum(self) -> "ObjectiveWeightsDTO":
        total = self.performance + self.quality + self.reach
        if total != 100:
            raise ValueError(
                f"weights must sum to 100, got {total} "
                f"(performance={self.performance}, "
                f"quality={self.quality}, reach={self.reach})"
            )
        return self


# ----------------------------------------------------- script CRUD shapes


class ScriptCreateRequest(ApiModel):
    """Body for ``POST /v1/studio/scripts``.

    Note: the customer never authors the script text directly. The
    server generates the DSL deterministically from the weights, so
    ``script_source`` is intentionally *not* in the request — that way
    we can guarantee everything in the DB went through the validator.
    """

    name: str = Field(min_length=1, max_length=160)
    line_item_id: Optional[str] = Field(
        default=None,
        description=(
            "Optional — scope the script to a single line item. "
            "Null = tenant-global script, re-usable across line items."
        ),
    )
    weights: ObjectiveWeightsDTO


# --- list/detail responses


class ScriptDTO(ApiModel):
    """Light-weight script payload for list views.

    Does **not** include ``script_source`` — list views can render a
    long list of scripts; we don't want to ship N×~6KB of DSL.
    Use :class:`ScriptDetailDTO` for single-script GET.
    """

    id: str
    tenant_id: str
    line_item_id: Optional[str] = None
    name: str
    status: str
    script_sha256: str
    size_bytes: int
    weights: ObjectiveWeightsDTO
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------- simulation DTOs


class DistributionStats(ApiModel):
    """Stable shape for the score distribution.

    The FE renders bars for the p10..p99 quantiles, the mean line,
    and the pct_above_500 callout. Values come straight from the
    score_simulator and are floats in DV360's 0..1000 score domain.
    """

    p10: float = 0.0
    p25: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p99: float = 0.0
    mean: float = 0.0
    stddev: float = 0.0
    pct_above_500: float = Field(
        default=0.0,
        description="Percent of scored impressions with score > 500.",
    )


class ImpressionScoreDTO(ApiModel):
    """One row in the top-winners or top-losers slice."""

    impression_id: str
    score: float
    used_signals: list[str] = Field(default_factory=list)


class SimulationRequest(ApiModel):
    """Body for ``POST /v1/studio/scripts/{id}/simulate``.

    All fields optional — sensible defaults run a 5k-impression
    synthetic simulation, which is what the FE wants on first click.
    """

    dataset_kind: Literal["synthetic", "floodlight_historical"] = "synthetic"
    n_impressions: int = Field(default=5000, ge=100, le=50_000)


class SimulationReportDTO(ApiModel):
    """Snapshot of one simulation run, returned to the FE inline.

    Persisted under :class:`SimulationRun`, but the FE doesn't need to
    care — we ship the same shape over the wire and in storage.
    """

    id: str
    script_id: str
    dataset_kind: str
    n_impressions: int
    n_scored: int
    n_excluded: int
    pct_above_500: float
    distribution: DistributionStats
    top_winners: list[ImpressionScoreDTO] = Field(default_factory=list)
    top_losers: list[ImpressionScoreDTO] = Field(default_factory=list)
    duration_ms: Optional[int] = None
    created_at: datetime


class ScriptDetailDTO(ScriptDTO):
    """Heavy-weight payload for the script detail view."""

    script_source: str
    latest_simulation: Optional[SimulationReportDTO] = None


__all__ = [
    "ObjectiveWeightsDTO",
    "ScriptCreateRequest",
    "ScriptDTO",
    "ScriptDetailDTO",
    "DistributionStats",
    "ImpressionScoreDTO",
    "SimulationRequest",
    "SimulationReportDTO",
]
