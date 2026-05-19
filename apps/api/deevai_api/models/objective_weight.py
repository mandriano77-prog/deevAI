"""ObjectiveWeight — the (performance, quality, reach) slider triplet
that generated a CustomBiddingScript.

Modelled 1:1 with the script for v1 (one weight row per script). When
we ship script versioning we'll keep the same shape: a v2 script gets
its own row + its own weights row, and the FK ``script_id`` remains
unique. The check constraint enforces ``perf + quality + reach = 100``
at the DB level so a bad migration can't slip past the API.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, new_uuid, utcnow


class ObjectiveWeight(Base):
    __tablename__ = "objective_weights"
    __table_args__ = (
        UniqueConstraint("script_id", name="uq_ow_script"),
        CheckConstraint(
            "performance_pct >= 0 AND performance_pct <= 100",
            name="ck_ow_performance_range",
        ),
        CheckConstraint(
            "quality_pct >= 0 AND quality_pct <= 100",
            name="ck_ow_quality_range",
        ),
        CheckConstraint(
            "reach_pct >= 0 AND reach_pct <= 100",
            name="ck_ow_reach_range",
        ),
        CheckConstraint(
            "performance_pct + quality_pct + reach_pct = 100",
            name="ck_ow_sum_100",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    script_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("custom_bidding_scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    performance_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    reach_pct: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ObjectiveWeight script={self.script_id[:8]} "
            f"P={self.performance_pct} Q={self.quality_pct} R={self.reach_pct}>"
        )
