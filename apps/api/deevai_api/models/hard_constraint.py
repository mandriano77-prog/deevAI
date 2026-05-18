"""HardConstraint — guardrails on an OptimizationStrategy."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class HardConstraint(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "hard_constraints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    optimization_strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("optimization_strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    metric: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=(
            "cpc | cpm | cpcv | vtr | viewability | fraud_rate | roas | "
            "revenue_per_day | volume_per_day"
        ),
    )
    operator: Mapped[str] = mapped_column(String(4), nullable=False, comment="gte | lte")
    value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    violation_policy: Mapped[str] = mapped_column(
        String(16),
        default="freeze",
        nullable=False,
        comment="freeze | throttle | kill | alert",
    )
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    def __repr__(self) -> str:
        return f"<HardConstraint {self.metric} {self.operator} {self.value}>"
