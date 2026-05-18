"""Tenant — the root entity. Every other domain object hangs off here.

A tenant is one paying account: one company / agency / brand. Users belong
to a tenant; integrations (Amazon DSP, AMC) belong to a tenant; runs and
decisions belong to a tenant. No cross-tenant access, ever."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_uuid,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(80), unique=True, nullable=False, index=True,
    )

    # Plan tier. Free during private beta; pricing tiers come later.
    plan: Mapped[str] = mapped_column(
        String(32), default="beta", nullable=False,
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False,
        comment="active | suspended | deleted",
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.slug} ({self.id})>"
