"""Action — declared conversion events outside media (visit, lead, purchase, …).

Actions carry weight (agent signal) and value_eur (business signal), which are
independent. They can be chained into a funnel via funnel_parent_id."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class Action(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    line_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("line_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[str] = mapped_column(
        "type",
        String(40),
        nullable=False,
        default="visit",
        comment="visit | lead | purchase | engagement | custom",
    )

    weight: Mapped[float] = mapped_column(Numeric(6, 2), default=1.0, nullable=False)
    value_eur: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    value_source: Mapped[str] = mapped_column(
        String(16),
        default="static",
        nullable=False,
        comment="static | dynamic | modeled",
    )
    value_currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)

    tracking_source: Mapped[str] = mapped_column(
        String(24),
        default="pixel",
        nullable=False,
        comment="pixel | s2s_postback | api | manual_upload",
    )
    attribution_window_hours: Mapped[int] = mapped_column(Integer, default=168, nullable=False)
    dedupe_rule: Mapped[str] = mapped_column(
        String(20),
        default="per_session",
        nullable=False,
        comment="per_session | per_user | first_only | every",
    )
    quality_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    funnel_parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("actions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    funnel_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        nullable=False,
        comment="active | paused | archived",
    )

    def __repr__(self) -> str:
        return f"<Action {self.name!r}>"
