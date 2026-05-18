"""Line item endpoints — CRUD for items under optimization."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id
from ..models import Advertiser, LineItem
from ..schemas.line_item import LineItemCreate, LineItemRead, LineItemUpdate

router = APIRouter(prefix="/line-items", tags=["line-items"])

_ALLOWED_MODES = frozenset({"observation_only", "approval_required", "auto_apply"})
_ALLOWED_STATUS = frozenset({"active", "paused", "archived"})


@router.get("", response_model=list[LineItemRead])
async def list_line_items(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> list[LineItem]:
    result = await db.execute(
        select(LineItem)
        .where(LineItem.tenant_id == tenant_id)
        .order_by(LineItem.name)
    )
    return list(result.scalars().all())


@router.get("/{line_item_id}", response_model=LineItemRead)
async def get_line_item(
    line_item_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> LineItem:
    line_item = await db.get(LineItem, line_item_id)
    if line_item is None or line_item.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Line item not found",
        )
    return line_item


@router.post("", response_model=LineItemRead, status_code=status.HTTP_201_CREATED)
async def create_line_item(
    payload: LineItemCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> LineItem:
    if payload.mode not in _ALLOWED_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"mode must be one of {sorted(_ALLOWED_MODES)}",
        )

    advertiser = await db.get(Advertiser, payload.advertiser_id)
    if advertiser is None or advertiser.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Advertiser not found",
        )

    ad_group_id = payload.amazon_ad_group_id or payload.amazon_line_item_id
    line_item = LineItem(
        tenant_id=tenant_id,
        advertiser_id=payload.advertiser_id,
        name=payload.name,
        amazon_line_item_id=payload.amazon_line_item_id,
        amazon_ad_group_id=ad_group_id,
        cpv_target=payload.cpv_target,
        current_max_bid=payload.current_max_bid,
        visit_event_id=payload.visit_event_id,
        mode=payload.mode,
    )
    db.add(line_item)
    await db.flush()
    return line_item


@router.patch("/{line_item_id}", response_model=LineItemRead)
async def update_line_item(
    line_item_id: str,
    payload: LineItemUpdate,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> LineItem:
    line_item = await db.get(LineItem, line_item_id)
    if line_item is None or line_item.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Line item not found",
        )

    data = payload.model_dump(exclude_unset=True)
    if "mode" in data and data["mode"] not in _ALLOWED_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"mode must be one of {sorted(_ALLOWED_MODES)}",
        )
    if "status" in data and data["status"] not in _ALLOWED_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"status must be one of {sorted(_ALLOWED_STATUS)}",
        )

    for key, value in data.items():
        setattr(line_item, key, value)
    await db.flush()
    return line_item
