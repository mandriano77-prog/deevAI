"""Auth endpoints — signup, login, me, password reset."""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import timedelta
from threading import Lock
from typing import Annotated, Deque

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..deps import get_current_user_claims, get_tenant_id
from ..models import Setting, Tenant, User, utcnow
from ..schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
)
from ..services.auth import (
    JWT_TTL_DAYS,
    create_access_token,
    create_password_reset_token,
    decode_password_reset_token,
    hash_password,
    verify_password,
)
from ..services.email import send_password_reset_email, send_welcome_email

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

FORGOT_PASSWORD_MESSAGE = (
    "Se l'indirizzo è registrato, riceverai un'email con le istruzioni "
    "per reimpostare la password."
)

# In-memory token bucket for ``POST /auth/demo-login``: max 10 calls/hour per IP.
# Single-process by design — demo logins are low-volume and the cost of getting
# rate-limit-bypass via multi-worker scale-out is acceptable for a sales demo.
DEMO_LOGIN_MAX_PER_HOUR = 10
DEMO_LOGIN_WINDOW_SECONDS = 3600
_demo_login_hits: dict[str, Deque[float]] = {}
_demo_login_lock = Lock()


def _demo_login_check_rate_limit(client_ip: str, *, now: float | None = None) -> bool:
    """Return True when the call is within budget; False when we must 429.

    Uses a sliding-window deque keyed by IP. The lock is held only for the
    bookkeeping — not across the JWT mint — so concurrency stays cheap.
    """
    ts = time.monotonic() if now is None else now
    with _demo_login_lock:
        bucket = _demo_login_hits.setdefault(client_ip, deque())
        cutoff = ts - DEMO_LOGIN_WINDOW_SECONDS
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= DEMO_LOGIN_MAX_PER_HOUR:
            return False
        bucket.append(ts)
        return True


def _reset_demo_login_buckets() -> None:
    """Test hook — clear the in-memory rate-limit table between tests."""
    with _demo_login_lock:
        _demo_login_hits.clear()


async def _send_welcome_after_signup(
    *,
    to: str,
    user_id: str,
    name: str | None,
    tenant_name: str,
) -> None:
    try:
        await send_welcome_email(
            to=to,
            user_id=user_id,
            name=name,
            tenant_name=tenant_name,
        )
    except Exception:
        log.exception("Welcome email failed for user_id=%s", user_id)


async def _send_reset_email_task(*, to: str, user_id: str, token: str) -> None:
    try:
        await send_password_reset_email(to=to, user_id=user_id, token=token)
    except Exception:
        log.exception("Password reset email failed for user_id=%s", user_id)


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: Annotated[SignupRequest, Body()],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Create a brand new tenant with the first owner user.

    Rejects duplicates by email or by tenant slug."""
    existing_tenant = await db.execute(
        select(Tenant).where(Tenant.slug == payload.tenant_slug)
    )
    if existing_tenant.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug '{payload.tenant_slug}' è già in uso",
        )

    existing_user = await db.execute(
        select(User).where(User.email == payload.email)
    )
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email già registrata",
        )

    tenant = Tenant(name=payload.tenant_name, slug=payload.tenant_slug)
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=str(payload.email),
        name=payload.full_name,
        password_hash=hash_password(payload.password),
        role="owner",
        status="active",
    )
    db.add(user)

    setting = Setting(
        tenant_id=tenant.id,
        default_cpv_target=0.50,
        digest_language="it",
        observation_only_until=utcnow() + timedelta(days=14),
        default_line_item_mode="approval_required",
    )
    db.add(setting)

    await db.flush()

    background_tasks.add_task(
        _send_welcome_after_signup,
        to=user.email,
        user_id=user.id,
        name=user.name,
        tenant_name=tenant.name,
    )

    token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        expires_in_days=JWT_TTL_DAYS,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: Annotated[LoginRequest, Body()],
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    result = await db.execute(
        select(User).where(User.email == str(payload.email))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide",
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabilitato",
        )

    tenant = await db.get(Tenant, user.tenant_id)
    assert tenant is not None

    token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        expires_in_days=JWT_TTL_DAYS,
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: Annotated[ForgotPasswordRequest, Body()],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Request a password reset link (always returns the same message)."""
    result = await db.execute(
        select(User).where(User.email == str(payload.email))
    )
    user = result.scalar_one_or_none()
    if user is not None and user.password_hash and user.status == "active":
        token = create_password_reset_token(user_id=user.id)
        background_tasks.add_task(
            _send_reset_email_task,
            to=user.email,
            user_id=user.id,
            token=token,
        )
    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: Annotated[ResetPasswordRequest, Body()],
    db: AsyncSession = Depends(get_session),
) -> MessageResponse:
    try:
        user_id = decode_password_reset_token(payload.token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link non valido o scaduto",
        ) from e

    user = await db.get(User, user_id)
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link non valido o scaduto",
        )

    user.password_hash = hash_password(payload.password)
    await db.flush()
    return MessageResponse(message="Password aggiornata. Puoi accedere con le nuove credenziali.")


@router.post("/demo-login", response_model=TokenResponse)
async def demo_login(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Mint a short-lived JWT for the public demo tenant.

    * **No credentials.** The caller provides nothing — we identify the demo
      tenant from the ``DEMO_TENANT_ID`` env var. If that var is unset the
      endpoint behaves as if it doesn't exist (404).
    * **Rate limited.** Max 10 calls/hour per source IP (in-memory token
      bucket). The 11th call gets 429.
    * **Read-only by construction.** The minted JWT carries the demo tenant's
      ``tid``; the ``DemoReadonlyMiddleware`` will then 403 any write attempt.
    """
    settings = get_settings()
    demo_tid = settings.demo_tenant_id
    if not demo_tid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo mode is not enabled on this environment",
        )

    client_ip = request.client.host if request.client else "unknown"
    if not _demo_login_check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Troppi tentativi di accesso al demo da questo IP. "
                "Riprova tra un'ora."
            ),
        )

    tenant = await db.get(Tenant, demo_tid)
    if tenant is None or not getattr(tenant, "is_demo", False):
        log.error(
            "demo-login: DEMO_TENANT_ID=%s but no matching demo tenant row found",
            demo_tid,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo tenant non inizializzato. Esegui lo seed.",
        )

    demo_user = await db.scalar(
        select(User)
        .where(User.tenant_id == tenant.id)
        .where(User.status == "active")
        .order_by(User.created_at.asc())
    )
    if demo_user is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo user non inizializzato. Esegui lo seed.",
        )

    from datetime import datetime, timezone

    from jose import jwt as _jwt

    from ..services.auth import JWT_ALGORITHM

    now = datetime.now(timezone.utc)
    payload = {
        "sub": demo_user.id,
        "tid": tenant.id,
        "role": demo_user.role,
        "is_demo": True,
        "iat": now,
        "exp": now + timedelta(hours=24),
    }
    token = _jwt.encode(payload, settings.api_secret_key, algorithm=JWT_ALGORITHM)

    return TokenResponse(
        access_token=token,
        user_id=demo_user.id,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        expires_in_days=1,
    )


@router.get("/me", response_model=MeResponse)
async def get_me(
    db: AsyncSession = Depends(get_session),
    claims: dict = Depends(get_current_user_claims),
):
    """Return the current authenticated user + tenant context.

    JWT claims carry `sub` (user_id) and `tid` (tenant_id, with a
    legacy `tenant_id` alias for backward-compat -- see
    `deps.get_tenant_id`). We hydrate both rows so the frontend can
    render the topbar (email, name, role, tenant name) without a
    second round-trip.
    """
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token senza sub",
        )
    tenant_id = get_tenant_id(claims)

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utente non trovato",
        )

    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant non trovato",
        )

    return MeResponse(
        user_id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        tenant_id=str(tenant.id),
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        tenant_is_demo=bool(getattr(tenant, "is_demo", False)),
    )
