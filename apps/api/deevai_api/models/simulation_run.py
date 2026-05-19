"""SimulationRun — one "Simulate" click against a Custom Bidding script.

Captures the *result shape* the FE renders (score distribution, counts,
duration) plus enough metadata to compare runs over time. The
distribution is stored as JSONB so we can evolve the keys without a
migration when we add new statistics (e.g. quantile curves, per-objective
contribution).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, new_uuid, utcnow


class SimulationRun(Base, TenantScopedMixin):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    script_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("custom_bidding_scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    dataset_kind: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="synthetic | floodlight_historical",
    )

    n_impressions: Mapped[int] = mapped_column(Integer, nullable=False)
    n_scored: Mapped[int] = mapped_column(Integer, nullable=False)
    n_excluded: Mapped[int] = mapped_column(Integer, nullable=False)

    distribution_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<SimulationRun script={self.script_id[:8]} "
            f"n={self.n_impressions} scored={self.n_scored}>"
        )
