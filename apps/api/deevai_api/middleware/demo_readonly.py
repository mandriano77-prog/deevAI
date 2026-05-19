"""Demo tenant read-only guard.

If a request carries a Bearer JWT whose ``tid`` claim matches the configured
``DEMO_TENANT_ID``, every state-changing call (POST / PATCH / PUT / DELETE)
to the protected surfaces — currently ``/v1/integrations/*`` and
``/v1/studio/scripts*`` — is short-circuited with a structured 403::

    {"detail": "Demo tenant is read-only", "demo": true}

Why a middleware instead of per-route deps?
-------------------------------------------
* It applies uniformly to every current and future route under the protected
  prefixes (incl. ones that don't exist yet, like Studio scripts).
* It runs *before* the router, so a bad write never executes (no half-applied
  side-effects, no audit log noise).
* GETs are always allowed so the demo user can navigate the full UI and the
  reporting layer keeps working end-to-end.

Exempt paths
------------
Public / auth-context paths are always allowed regardless of method so the FE
can still hydrate the topbar and the docs/health pages stay reachable from a
demo session::

    /v1/auth/me, /health, /docs, /openapi.json, /v1/auth/demo-login

The middleware fails open on unparseable / unsigned / expired tokens — those
get their normal 401 from the downstream auth dependency. We only enforce when
we can prove the caller is the demo tenant.
"""

from __future__ import annotations

import logging
from typing import Iterable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ..config import get_settings
from ..services.auth import decode_access_token

log = logging.getLogger(__name__)

# Methods that count as "writes". OPTIONS / HEAD / GET always pass through.
_WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

# Path prefixes that the demo tenant is NOT allowed to write to.
# We match on path startswith — keeping this list explicit (vs. blocking
# everything non-GET) means the demo can still hit POST endpoints that are
# safe-by-design (e.g. ``/v1/auth/demo-login`` itself).
_PROTECTED_PREFIXES: tuple[str, ...] = (
    "/v1/integrations",
    "/v1/studio/scripts",
)

# Paths that are always allowed — even for the demo tenant, even for writes.
_ALWAYS_ALLOWED_PATHS: frozenset[str] = frozenset(
    {
        "/v1/auth/me",
        "/v1/auth/demo-login",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


def _path_is_protected(path: str, prefixes: Iterable[str] = _PROTECTED_PREFIXES) -> bool:
    """True when ``path`` falls under one of the demo-locked prefixes."""
    for prefix in prefixes:
        base = prefix.rstrip("/")
        if path == base or path.startswith(base + "/"):
            return True
    return False


def _extract_bearer_token(request: Request) -> str | None:
    """Pull the JWT out of the ``Authorization: Bearer …`` header (None if missing)."""
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth:
        return None
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


class DemoReadonlyMiddleware(BaseHTTPMiddleware):
    """Block writes for the configured demo tenant. No-op when DEMO_TENANT_ID is unset."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()
        demo_tid = settings.demo_tenant_id

        # No demo tenant configured → middleware is fully inert.
        if not demo_tid:
            return await call_next(request)

        method = request.method.upper()
        # GET / HEAD / OPTIONS always allowed.
        if method not in _WRITE_METHODS:
            return await call_next(request)

        path = request.url.path
        if path in _ALWAYS_ALLOWED_PATHS:
            return await call_next(request)

        if not _path_is_protected(path):
            return await call_next(request)

        # Only enforce when we can prove this request is the demo tenant.
        # Unauthenticated / malformed tokens fall through — the downstream
        # auth dependency will return its normal 401.
        token = _extract_bearer_token(request)
        if not token:
            return await call_next(request)

        try:
            claims = decode_access_token(token)
        except ValueError:
            return await call_next(request)

        tid = claims.get("tid") or claims.get("tenant_id")
        if tid != demo_tid:
            return await call_next(request)

        log.info(
            "demo_readonly: blocked %s %s for demo tenant %s",
            method,
            path,
            demo_tid,
        )
        return JSONResponse(
            status_code=403,
            content={"detail": "Demo tenant is read-only", "demo": True},
        )
