"""FastAPI dependencies — current user, current tenant, DB session.

Resolution order for the current tenant:
  1. JWT in `Authorization: Bearer <token>` header (preferred — production path)
  2. `X-Tenant-Id` header (dev fallback, deprecated as soon as the FE
     calls signup/login)

The JWT carries `sub` (user_id), `tid` (tenant_id) and `role`. The
fallback header is here only to make local curl/Swagger testing easy
without forcing a login dance every time."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select

from .db import get_session
from .services.auth import decode_access_token

if TYPE_CHECKING:
    from .models.base import Base


bearer_scheme = HTTPBearer(auto_error=False)


def extract_tenant_id(claims: dict) -> str | None:
    """Return the tenant id from JWT claims or ``None`` if absent.

    Reads the canonical ``tid`` claim, falling back to the legacy
    ``tenant_id`` alias so tokens issued before the uniformity refactor
    keep working until they expire. Non-raising — use this in code
    paths (e.g. middleware) that need to peek at the claim without
    forcing a 401 when missing.

    NOTE: the ``tenant_id`` fallback is DEPRECATED and exists only for
    backward-compat (see services/auth.py). Remove after 2026-08 once
    every active JWT has been re-issued with both claims.
    """
    tid = claims.get("tid") or claims.get("tenant_id")
    if isinstance(tid, str) and tid:
        return tid
    return None


def get_tenant_id(claims: dict) -> str:
    """Resolve the tenant id from JWT claims, raising 401 if missing.

    Thin wrapper around :func:`extract_tenant_id` for the common case
    where a route requires a tenant claim and should reject the
    request otherwise. See :func:`extract_tenant_id` for details on
    the canonical / legacy claim names.
    """
    tid = extract_tenant_id(claims)
    if tid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing tenant claim",
        )
    return tid


async def get_current_tenant_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> str:
    """Resolve the current tenant from JWT (primary) or X-Tenant-Id header (dev)."""
    if credentials and credentials.scheme.lower() == "bearer":
        try:
            payload = decode_access_token(credentials.credentials)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e),
            ) from e
        return get_tenant_id(payload)

    if x_tenant_id:
        return x_tenant_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide a Bearer token or X-Tenant-Id header",
    )



async def get_optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str | None:
    """JWT sub when Bearer present; None for dev X-Tenant-Id-only requests."""
    if credentials and credentials.scheme.lower() == "bearer":
        try:
            payload = decode_access_token(credentials.credentials)
            return payload.get("sub")
        except ValueError:
            return None
    return None


async def get_current_user_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Returns the JWT claims dict. Raises 401 if no token or invalid."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    try:
        return decode_access_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e),
        ) from e


def tenant_scoped_select(model: type["Base"], tenant_id: str) -> Select:
    """Build a SELECT already filtered by tenant_id."""
    return select(model).where(model.tenant_id == tenant_id)  # type: ignore[attr-defined]


# Convenience aliases — annotate routes with these.
TenantId = Depends(get_current_tenant_id)
DbSession = Depends(get_session)
UserClaims = Depends(get_current_user_claims)


__all__ = [
    "get_current_tenant_id",
    "get_optional_user_id",
    "get_current_user_claims",
    "get_tenant_id",
    "extract_tenant_id",
    "tenant_scoped_select",
    "TenantId",
    "DbSession",
    "UserClaims",
]
