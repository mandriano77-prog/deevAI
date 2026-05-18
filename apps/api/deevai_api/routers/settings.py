"""Tenant settings — read and update optimizer parameters."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Body, Depends

from ..routing import CamelCaseRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id, get_optional_user_id
from ..services.audit import snapshot_row, write_audit
from ..models import Setting, utcnow
from ..schemas.setting import SettingRead, SettingUpdate

router = CamelCaseRouter(prefix="/settings", tags=["settings"])


async def _get_or_create_tenant_setting(
    db: AsyncSession, tenant_id: str,
) -> Setting:
    result = await db.execute(
        select(Setting).where(Setting.tenant_id == tenant_id).limit(1),
    )
    setting = result.scalar_one_or_none()
    if setting is not None:
        return setting

    setting = Setting(
        tenant_id=tenant_id,
        default_cpv_target=0.50,
        digest_language="it",
        observation_only_until=utcnow() + timedelta(days=14),
        default_line_item_mode="approval_required",
    )
    db.add(setting)
    await db.flush()
    await db.refresh(setting)
    return setting


@router.get("", response_model=SettingRead)
async def get_settings(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> Setting:
    return await _get_or_create_tenant_setting(db, tenant_id)


@router.patch("", response_model=SettingRead)
async def update_settings(
    payload: Annotated[SettingUpdate, Body()],
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> Setting:
    setting = await _get_or_create_tenant_setting(db, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return setting
    before = snapshot_row(setting)
    for key, value in updates.items():
        setattr(setting, key, value)
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="settings",
        entity_id=setting.id,
        action="update",
        before=before,
        after=snapshot_row(setting),
    )
    await db.flush()
    await db.refresh(setting)
    return setting
