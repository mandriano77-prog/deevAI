"""LineItem — a DSP line item under management.

This is the unit that DeevAI optimizes. Each line item has its own CPV
target, current max_bid, and lifecycle status. The agent's runs and
decisions are keyed off LineItem.

`mode` controls how the agent treats this line item:
- observation_only : compute decisions but never apply (default first 14 days)
- approval_required: compute, propose, require human approval to apply
- auto_apply      : compute and apply directly (advanced users only)
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class LineItem(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "line_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    advertiser_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("advertisers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Amazon-side identifiers
    amazon_line_item_id: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True,
    )
    # Bid Adjustments API associates rules with ad groups (often == line item id).
    amazon_ad_group_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True,
    )
    # UUID returned by POST /dsp/rules/adjustments — reuse for weekly PATCH.
    amazon_bid_adjustment_rule_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)

    # Optimization target
    cpv_target: Mapped[float] = mapped_column(
        Numeric(10, 4), nullable=False,
        comment="Cost per visit target, in the advertiser's currency",
    )
    current_max_bid: Mapped[float | None] = mapped_column(Numeric(10, 4))

    # The pixel/conversion event ID used as 'visit' for this line item
    visit_event_id: Mapped[str | None] = mapped_column(String(80))

    # Lifecycle
    mode: Mapped[str] = mapped_column(
        String(32), default="observation_only", nullable=False,
        comment="observation_only | approval_required | auto_apply",
    )
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False,
        comment="active | paused | archived",
    )

    def __repr__(self) -> str:
        return f"<LineItem {self.name} (mode={self.mode})>"
