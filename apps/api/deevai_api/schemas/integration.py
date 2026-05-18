"""Integration + DV360 OAuth request/response shapes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationRead(BaseModel):
    """Generic read shape — works for any provider."""
    id: str
    provider: str
    name: str
    status: str
    # Provider-specific bag (DV360 → {advertiser_id, partner_id}).
    provider_config: dict | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntegrationConnectResponse(BaseModel):
    """Returned by the connect endpoint so the FE can redirect to the
    provider's consent screen."""
    integration_id: str
    authorize_url: str


# ---------------------------------------------------------------------------
# DV360 (Google Display & Video 360)
# ---------------------------------------------------------------------------


class Dv360ConnectRequest(BaseModel):
    """FE → POST /integrations/dv360/connect.

    The customer gives us their Google OAuth client_id/secret (created
    in Google Cloud Console under APIs & Services → Credentials, type
    "Web application", with the DeevAI callback URL whitelisted).
    """
    name: str = Field(min_length=1, max_length=160, default="DV360")
    client_id: str = Field(min_length=10)
    client_secret: str = Field(min_length=10)


class Dv360AdvertiserRead(BaseModel):
    """One row in the advertiser picker after a successful callback."""
    advertiser_id: str
    display_name: str
    partner_id: str | None = None
    currency_code: str | None = None
    timezone: str | None = None
    entity_status: str | None = None


class Dv360CallbackResult(BaseModel):
    """Returned at the end of the DV360 OAuth callback."""
    integration_id: str
    status: str
    advertisers: list[Dv360AdvertiserRead]


class Dv360SelectAdvertiserRequest(BaseModel):
    """FE → POST /integrations/{id}/dv360/select-advertiser."""
    advertiser_id: str = Field(min_length=1)
    partner_id: str | None = None
