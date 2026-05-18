"""Application settings loaded from environment variables.

We use pydantic-settings so misconfigured envs fail loudly at startup
instead of silently at runtime."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration. All values come from env vars (or .env)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ──
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "DeevAI"
    app_base_url: str = "http://localhost:3000"

    # ── API ──
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = Field(min_length=16)

    # ── Database ──
    database_url: str

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Render/Railway expose postgresql:// — asyncpg needs the +asyncpg driver."""

        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    # ── Google DV360 OAuth ──
    # Per-tenant OAuth (the tenant provides their own client_id/secret in
    # the connect payload), so the only global setting we need is the
    # redirect_uri the FE will receive the callback on.
    #
    # The redirect lands on the Next.js page `/onboarding`, which at
    # mount time forwards the (code, state) pair to the backend via the
    # standard /api/v1 rewrite. Whatever value lives here MUST match
    # the "Authorized redirect URI" registered in the tenant's Google
    # Cloud OAuth client (otherwise Google rejects with redirect_uri_mismatch).
    dv360_redirect_uri: str = "http://localhost:3000/onboarding"

    # ── AWS / KMS (for tenant-credential vault) ──
    aws_region: str = "eu-central-1"
    kms_key_id: Optional[str] = None

    # ── LLM (for digest generation) ──
    llm_provider: Literal["anthropic", "openai", "none"] = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    anthropic_api_key: Optional[str] = None

    # ── DSP apply (bid modifier writes) ──
    # Dry-run logs payloads but never hits DV360. Set DSP_DRY_RUN=false only
    # when OAuth + advertiser are confirmed live.
    dsp_dry_run: bool = True

    # ── Email (Resend) ──
    resend_api_key: Optional[str] = None
    email_from: str = "DeevAI <onboarding@resend.dev>"

    # ── Observability ──
    log_level: str = "INFO"
    sentry_dsn: Optional[str] = None

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — call this everywhere instead of instantiating."""
    return Settings()  # type: ignore[call-arg]
