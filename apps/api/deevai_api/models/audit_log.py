"""AuditLog — immutable record of mutations for compliance and meta-agent trace."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class AuditLog(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    actor_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(
        String(20),
        default="user",
        nullable=False,
        comment="user | setup_agent | tuning_agent | system",
    )
    proposal_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agent_proposals.id", ondelete="SET NULL"),
        nullable=True,
    )
    entity: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="create | update | delete | apply | revert",
    )
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog {self.entity} {self.action}>"
