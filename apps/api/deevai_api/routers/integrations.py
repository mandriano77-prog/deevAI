"""Integration endpoints — DV360 OAuth user-consent flow.

Flow:
  1) POST /integrations/dv360/connect
     - FE sends the tenant's Google OAuth client_id/secret.
     - We create an Integration row in status='pending', store the
       client_secret encrypted, sign a state token, return the Google
       authorize URL.
  2) (User clicks → goes to Google → consents → Google redirects to us)
  3) GET /integrations/dv360/callback?code=...&state=...
     - Verify state, exchange code for refresh_token, store encrypted,
       list the visible advertisers, return them to the FE.
  4) POST /integrations/{id}/dv360/select-advertiser
     - User picks which advertiser deevAI should manage; we persist
       advertiser_id + partner_id into provider_config.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id
from ..models import Integration
from ..schemas.integration import (
    Dv360AdvertiserRead,
    Dv360CallbackResult,
    Dv360ConnectRequest,
    Dv360SelectAdvertiserRequest,
    IntegrationConnectResponse,
    IntegrationRead,
)
from ..services import dv360_advertisers, dv360_oauth
from ..services.security import sign_state, verify_state

log = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationRead])
async def list_integrations(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> list[Integration]:
    """List all integrations for the current tenant."""
    result = await db.execute(
        select(Integration).where(Integration.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# DV360 OAuth flow
# ---------------------------------------------------------------------------


@router.post(
    "/dv360/connect",
    response_model=IntegrationConnectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def dv360_connect(
    payload: Dv360ConnectRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> IntegrationConnectResponse:
    """Start the DV360 OAuth flow. Creates a pending Integration row and
    returns the Google authorize URL for the FE to redirect to."""

    integration = Integration(
        tenant_id=tenant_id,
        provider="dv360",
        name=payload.name,
        client_id=payload.client_id,
        status="pending",
    )
    integration.client_secret = payload.client_secret  # encrypted via vault

    db.add(integration)
    await db.flush()

    state = sign_state(integration.id)
    authorize_url = dv360_oauth.build_authorize_url(
        client_id=payload.client_id,
        state=state,
    )
    return IntegrationConnectResponse(
        integration_id=integration.id,
        authorize_url=authorize_url,
    )


@router.get(
    "/dv360/callback",
    response_model=Dv360CallbackResult,
)
async def dv360_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="Signed state token"),
    error: str | None = Query(None, description="If user denied consent"),
    db: AsyncSession = Depends(get_session),
) -> Dv360CallbackResult:
    """Receive the redirect from Google. NO tenant header (we recover
    the tenant via the signed state)."""

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User denied consent on Google: {error}",
        )

    try:
        integration_id = verify_state(state)
    except ValueError as e:
        log.warning("Invalid DV360 state token: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state: {e}",
        ) from e

    integration = await db.get(Integration, integration_id)
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    if integration.provider != "dv360":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Integration {integration.id} is not a DV360 integration",
        )

    client_secret = integration.client_secret
    if not client_secret or not integration.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration missing client credentials",
        )

    try:
        tokens = await dv360_oauth.exchange_code_for_tokens(
            code=code,
            client_id=integration.client_id,
            client_secret=client_secret,
        )
    except RuntimeError as e:
        integration.status = "error"
        integration.last_error = str(e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    integration.refresh_token = tokens.refresh_token

    try:
        advertisers = await dv360_advertisers.list_advertisers(
            access_token=tokens.access_token,
        )
    except RuntimeError as e:
        integration.status = "error"
        integration.last_error = str(e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    integration.status = "connected"
    integration.last_error = None

    return Dv360CallbackResult(
        integration_id=integration.id,
        status=integration.status,
        advertisers=[
            Dv360AdvertiserRead(
                advertiser_id=a.advertiser_id,
                display_name=a.display_name,
                partner_id=a.partner_id,
                currency_code=a.currency_code,
                timezone=a.timezone,
                entity_status=a.entity_status,
            )
            for a in advertisers
        ],
    )


@router.post(
    "/{integration_id}/dv360/select-advertiser",
    response_model=IntegrationRead,
)
async def dv360_select_advertiser(
    integration_id: str,
    payload: Dv360SelectAdvertiserRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> Integration:
    """Pin the integration to a specific DV360 advertiser.

    Persists into `provider_config` JSONB. Keys: `advertiser_id`, `partner_id`.
    """
    integration = await db.get(Integration, integration_id)
    if integration is None or integration.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    if integration.provider != "dv360":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Integration {integration.id} is not a DV360 integration",
        )

    config = dict(integration.provider_config or {})
    config["advertiser_id"] = payload.advertiser_id
    if payload.partner_id:
        config["partner_id"] = payload.partner_id
    integration.provider_config = config
    return integration
