"""Decision — one bid-adjustment proposal generated during a Run.

Each Decision corresponds to one (targeting_module, targeting_key, value)
combination — i.e. one row in the Amazon bid adjustment payload. The
human-in-the-loop flow uses the `status` column: proposed → approved or
rejected → (if approved) applied."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class Decision(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The targeting term this decision applies to.
    # These match the bidagent ModifierTerm shape exactly so we can
    # round-trip without translation.
    targeting_module: Mapped[str] = mapped_column(String(40), nullable=False)
    targeting_key: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(String(240), nullable=False)
    field_label: Mapped[str | None] = mapped_column(String(240))

    # The actual decision
    previous_modifier: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    new_modifier: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)

    # Why
    reason: Mapped[str] = mapped_column(
        String(40), nullable=False,
        comment=(
            "under_target | over_target | on_target | insufficient_volume | "
            "anomalous_ctr | low_viewability | zero_visits | "
            "exploration_revive | smoothed"
        ),
    )
    note: Mapped[str | None] = mapped_column(Text)

    # Observed metrics that led to this decision (for explainability)
    observed_impressions: Mapped[int | None] = mapped_column(Integer)
    observed_clicks: Mapped[int | None] = mapped_column(Integer)
    observed_visits: Mapped[int | None] = mapped_column(Integer)
    observed_cpv: Mapped[float | None] = mapped_column(Numeric(10, 4))

    # Human-in-the-loop state
    status: Mapped[str] = mapped_column(
        String(32), default="proposed", nullable=False,
        comment="proposed | approved | rejected | applied | failed_to_apply",
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_error: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return (
            f"<Decision {self.targeting_module}.{self.targeting_key}={self.value} "
            f"{self.previous_modifier}→{self.new_modifier} [{self.status}]>"
        )
