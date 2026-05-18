"""M.AI conversational agent audit log."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class MaiLog(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "mai_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    line_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("line_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    prompt: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(64))
    proposal: Mapped[dict | None] = mapped_column(JSONB)
    action: Mapped[str] = mapped_column(
        String(24),
        default="planned",
        nullable=False,
        comment="planned | executed | dismissed",
    )
    payload: Mapped[dict | None] = mapped_column(JSONB)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
