"""Setting — per-tenant configuration of the agent.

Holds optimizer parameters and hygiene rules. One row per tenant. The
defaults below are the "safe" values we ship to a new customer; they can
be overridden in the UI."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Numeric, String, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class Setting(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # ── Optimizer parameters ──
    default_cpv_target: Mapped[float] = mapped_column(
        Numeric(10, 4), default=0.50, nullable=False,
    )
    tolerance_band: Mapped[float] = mapped_column(
        Numeric(4, 3), default=0.20, nullable=False,
        comment="±20% around target = on_target",
    )
    max_step_per_run: Mapped[float] = mapped_column(
        Numeric(4, 3), default=0.30, nullable=False,
        comment="Cap on modifier delta per weekly run",
    )
    max_modifier: Mapped[float] = mapped_column(
        Numeric(4, 2), default=2.50, nullable=False,
    )
    min_modifier_active: Mapped[float] = mapped_column(
        Numeric(4, 2), default=0.30, nullable=False,
    )
    exploration_revive_after_runs: Mapped[int] = mapped_column(
        Integer, default=4, nullable=False,
    )
    exploration_revive_modifier: Mapped[float] = mapped_column(
        Numeric(4, 2), default=0.50, nullable=False,
    )

    # ── Hygiene rules ──
    min_impressions_for_action: Mapped[int] = mapped_column(
        Integer, default=500, nullable=False,
    )
    min_visits_for_strong_action: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False,
    )
    anomalous_ctr_threshold: Mapped[float] = mapped_column(
        Numeric(5, 4), default=0.0400, nullable=False,
        comment="CTR above this triggers click-farm filter",
    )
    min_viewability: Mapped[float] = mapped_column(
        Numeric(4, 3), default=0.400, nullable=False,
    )

    # ── Lifecycle / observation-only ──
    observation_only_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="No live writes before this date — deevAI's 14-day promise",
    )
    default_line_item_mode: Mapped[str] = mapped_column(
        String(32),
        default="approval_required",
        nullable=False,
        comment="Mode applied to line items after observation_only_until",
    )
    digest_language: Mapped[str] = mapped_column(
        String(8), default="it", nullable=False,
        comment="ISO 639-1 language code for the weekly digest",
    )
    digest_delivery_email: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Setting tenant={self.tenant_id}>"
