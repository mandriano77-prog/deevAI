"""Auth endpoints — signup, login, me, password reset."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user_claims
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


@router.get("/me", response_model=MeResponse)
async def get_me(
    db: AsyncSession = Depends(get_session),
    claims: dict = Depends(get_current_user_claims),
):
    """Return the current authenticated user + tenant context.

    JWT claims carry `sub` (user_id) and `tenant_id`. We hydrate both rows so
    the frontend can render the topbar (email, name, role, tenant name) without
    a second round-trip.
    """
    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token senza sub/tenant_id",
        )

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
    )
