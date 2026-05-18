"""Tenant endpoints — minimal: read current tenant.

Tenant creation happens via the seed script for now (Sprint 1.3).
Signup/login + tenant provisioning come in Sprint 1.4."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id
from ..models import Tenant
from ..schemas.tenant import TenantRead

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/me", response_model=TenantRead)
async def get_my_tenant(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> Tenant:
    """Return the current tenant (identified by the X-Tenant-Id header)."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return tenant
