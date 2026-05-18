"""User — a person who can log into deevAI and act on a Tenant.

For MVP we have one user per tenant (the owner). The model is already
multi-user shape so we can add team members later without migrations."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class User(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True,
    )
    name: Mapped[str | None] = mapped_column(String(160))

    # bcrypt hash; never store plaintext. Optional for OAuth-only users (later).
    password_hash: Mapped[str | None] = mapped_column(String(120))

    role: Mapped[str] = mapped_column(
        String(32), default="owner", nullable=False,
        comment="owner | member | viewer",
    )
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False,
        comment="active | invited | disabled",
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
