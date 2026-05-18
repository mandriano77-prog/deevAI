"""Declarative base + reusable mixins.

Every domain table that holds tenant data inherits from `TenantScopedMixin`
so we never forget the `tenant_id` column. The dependency helpers in
`deps.py` enforce that queries filter by `tenant_id` automatically.

Encryption pattern: columns that hold secrets (refresh tokens, client
secrets, etc.) are declared as `LargeBinary` and accessed via paired
helper properties that go through `services.secrets_vault`. The vault
abstracts away whether we're encrypting with AWS KMS, a local Fernet key,
or anything else — see Sprint 1.3."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Always tz-aware UTC — never naive datetimes anywhere."""
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Root for all ORM models."""


class TimestampMixin:
    """Adds created_at / updated_at to a model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class TenantScopedMixin:
    """Every table that holds tenant data must use this.

    Queries from API code must filter by `tenant_id`. Use the
    `tenant_scoped_select(...)` helper in deps.py — never call
    `session.execute(select(Model))` without a tenant filter."""

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
