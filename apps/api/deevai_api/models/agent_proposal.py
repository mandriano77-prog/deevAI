"""AgentProposal — setup and tuning agent suggestions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class AgentProposal(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "agent_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    agent_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="setup | tuning",
    )

    line_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("line_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    brief: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    proposed_changes: Mapped[list] = mapped_column(JSONB, nullable=False)
    expected_impact: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        comment="pending | approved | rejected | applied | reverted | failed",
    )
    auto_applicable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    approver_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    post_mortem_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    post_mortem: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    llm_model: Mapped[str | None] = mapped_column(String(60))
    llm_input_tokens: Mapped[int | None] = mapped_column(Integer)
    llm_output_tokens: Mapped[int | None] = mapped_column(Integer)

    def __repr__(self) -> str:
        return f"<AgentProposal {self.agent_type} {self.id[:8]} status={self.status}>"
