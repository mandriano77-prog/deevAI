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
        tid = payload.get("tid")
        if not tid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing tenant_id claim",
            )
        return tid

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
    "tenant_scoped_select",
    "TenantId",
    "DbSession",
    "UserClaims",
]
