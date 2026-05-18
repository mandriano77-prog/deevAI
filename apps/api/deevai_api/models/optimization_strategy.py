"""OptimizationStrategy — metric-agnostic KPI targets (single or blended)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class OptimizationStrategy(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "optimization_strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    line_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("line_items.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
        index=True,
    )

    mode: Mapped[str] = mapped_column(
        String(20),
        default="single",
        nullable=False,
        comment="single | blended_2 | blended_3",
    )

    primary_metric: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        comment="cpv | cpc | cpcv | cpm | cpa | roas | custom_action",
    )
    primary_target: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    primary_weight: Mapped[float] = mapped_column(
        Numeric(5, 2),
        default=100.0,
        nullable=False,
    )

    secondary_metric: Mapped[str | None] = mapped_column(String(40), nullable=True)
    secondary_target: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    secondary_weight: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    tertiary_metric: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tertiary_target: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    tertiary_weight: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    primary_action_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("actions.id", ondelete="SET NULL"),
        nullable=True,
    )

    tolerance_band: Mapped[float] = mapped_column(Numeric(4, 3), default=0.20, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    def __repr__(self) -> str:
        scope = self.line_item_id or "tenant-default"
        return f"<OptimizationStrategy {self.mode} {self.primary_metric} ({scope})>"
