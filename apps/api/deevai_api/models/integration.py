"""Integration — a tenant's connection to a DSP (Google DV360 for now).

deevAI is single-DSP by design: each tenant has one DV360 integration.
The columns are still provider-tagged so that if we ever add a new DSP
on the same product (e.g. TTD as a paid add-on) it's a row insert, not
a schema change.

Encryption:
- `client_secret_ciphertext` and `refresh_token_ciphertext` hold the bytes
  emitted by `services.secrets_vault.encrypt()`.
- The plaintext properties (`client_secret`, `refresh_token`) go through
  the vault on every access. NEVER expose the ciphertext directly to
  application code — go through the property.
- Never log either form. The `__repr__` is intentionally minimal."""

from __future__ import annotations

from sqlalchemy import LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..services.secrets_vault import decrypt, encrypt
from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class Integration(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # Provider — defaults to "dv360". Future-proofed for additional DSPs.
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="dv360",
    )

    # Human label for the integration in the UI
    name: Mapped[str] = mapped_column(String(160), nullable=False)

    # ── Credentials (encrypted at rest) ──
    client_id: Mapped[str | None] = mapped_column(String(160))
    client_secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)

    # ── Provider-specific config bag (JSONB) ──
    # For DV360 this holds {advertiser_id, partner_id}. New providers
    # (TTD, Beeswax, …) put their per-tenant identifiers here without
    # growing the schema.
    provider_config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None,
    )

    # ── Lifecycle ──
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False,
        comment="pending | connected | error | disconnected",
    )
    last_health_check_at: Mapped[str | None] = mapped_column(String(40))  # ISO ts
    last_error: Mapped[str | None] = mapped_column(String(500))

    # ── Encrypted-field accessors ──
    # Properties — not columns — so SQLAlchemy doesn't get confused.

    @property
    def client_secret(self) -> str | None:
        if self.client_secret_ciphertext is None:
            return None
        return decrypt(self.client_secret_ciphertext)

    @client_secret.setter
    def client_secret(self, value: str | None) -> None:
        self.client_secret_ciphertext = encrypt(value) if value else None

    @property
    def refresh_token(self) -> str | None:
        if self.refresh_token_ciphertext is None:
            return None
        return decrypt(self.refresh_token_ciphertext)

    @refresh_token.setter
    def refresh_token(self, value: str | None) -> None:
        self.refresh_token_ciphertext = encrypt(value) if value else None

    def __repr__(self) -> str:
        # Deliberately does NOT include any credentials, even partial.
        return f"<Integration {self.provider} status={self.status}>"
