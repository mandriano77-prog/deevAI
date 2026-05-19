"""CustomBiddingScript — a DV360 (or other DSP) Custom Bidding scoring script.

One row per script generated through the Studio. Carries the raw DSL
source, its sha256 digest (for de-dupe + change detection), and a
lifecycle ``status`` that tracks where the script is in the pipeline:

    draft → simulated → uploaded → active → archived

``line_item_id`` is optional: a script can be scoped to a single line
item, or live "globally" inside the tenant (re-usable across line items).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class CustomBiddingScript(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "custom_bidding_scripts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_cbs_tenant_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    line_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("line_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False, index=True,
        comment="draft | simulated | uploaded | active | archived",
    )

    script_source: Mapped[str] = mapped_column(Text, nullable=False)
    script_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CustomBiddingScript name={self.name!r} status={self.status} "
            f"sha={self.script_sha256[:8]}>"
        )
