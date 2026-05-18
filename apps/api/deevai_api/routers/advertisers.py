"""Advertiser endpoints — register DSP advertisers under an integration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id
from ..models import Advertiser, Integration
from ..schemas.advertiser import AdvertiserCreate, AdvertiserRead

router = APIRouter(prefix="/advertisers", tags=["advertisers"])


@router.get("", response_model=list[AdvertiserRead])
async def list_advertisers(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> list[Advertiser]:
    result = await db.execute(
        select(Advertiser)
        .where(Advertiser.tenant_id == tenant_id)
        .order_by(Advertiser.name)
    )
    return list(result.scalars().all())


@router.post("", response_model=AdvertiserRead, status_code=status.HTTP_201_CREATED)
async def create_advertiser(
    payload: AdvertiserCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> Advertiser:
    integration = await db.get(Integration, payload.integration_id)
    if integration is None or integration.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    advertiser = Advertiser(
        tenant_id=tenant_id,
        integration_id=payload.integration_id,
        amazon_advertiser_id=payload.amazon_advertiser_id,
        name=payload.name,
        currency=payload.currency.upper(),
        country=payload.country.upper(),
    )
    db.add(advertiser)
    await db.flush()
    return advertiser
