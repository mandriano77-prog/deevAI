"""Advertiser — a DSP advertiser account managed under an Integration.

One Integration (= one Amazon seat) can hold multiple advertisers
(e.g. an agency seat managing several brands). DeevAI optimizes each
advertiser independently."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class Advertiser(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "advertisers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    integration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Amazon-side identifiers
    amazon_advertiser_id: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="IT", nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False,
        comment="active | paused | archived",
    )

    def __repr__(self) -> str:
        return f"<Advertiser {self.name} ({self.amazon_advertiser_id})>"
