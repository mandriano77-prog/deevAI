"""JWT claims uniformity tests — canonical ``tid`` + legacy ``tenant_id``.

Covers the chore/auth-claims-uniformity refactor:

* tokens issued post-fix carry **both** the canonical short claim
  ``tid`` and the legacy long alias ``tenant_id``;
* the ``GET /v1/auth/me`` endpoint accepts tokens that have only
  ``tid``, only ``tenant_id`` (simulated legacy issuance), and
  rejects tokens with neither;
* the shared :func:`get_tenant_id` helper raises a 401 — not a
  generic 500 — when the claim is missing.

We mint tokens directly via the jose encoder for the legacy-only
case (so we can simulate a token that pre-dates the alias addition
without having to monkey-patch ``create_access_token``).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator as AI

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from jose import jwt

os.environ.setdefault("API_SECRET_KEY", "test-secret-key-32-chars-min!!")

from deevai_api.config import get_settings  # noqa: E402
from deevai_api.db import get_session  # noqa: E402
from deevai_api.deps import extract_tenant_id, get_tenant_id  # noqa: E402
from deevai_api.main import app  # noqa: E402
from deevai_api.models import Tenant, User  # noqa: E402
from deevai_api.services.auth import (  # noqa: E402
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
)


# ---------------------------------------------------------------- helpers


def _mint_legacy_token(*, user_id: str, tenant_id: str, role: str = "owner") -> str:
    """Mint a token that carries only ``tenant_id`` (pre-uniformity shape)."""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,  # legacy claim only — no `tid`
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.api_secret_key, algorithm=JWT_ALGORITHM)


def _mint_claimless_token(*, user_id: str) -> str:
    """Mint a token with no tenant claim of any kind."""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "role": "owner",
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.api_secret_key, algorithm=JWT_ALGORITHM)


async def _seed_user(db_session, slug: str) -> tuple[Tenant, User]:
    tenant = Tenant(name=f"T-{slug}", slug=slug, plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"{slug}@example.com",
        name="Alice",
        password_hash=hash_password("hunter2-not-used"),
        role="owner",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return tenant, user


async def _client(db_session) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AI:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ========================================================== helper unit tests


def test_extract_tenant_id_prefers_tid() -> None:
    assert extract_tenant_id({"tid": "tenant-canonical", "tenant_id": "legacy"}) == "tenant-canonical"


def test_extract_tenant_id_falls_back_to_tenant_id() -> None:
    assert extract_tenant_id({"tenant_id": "legacy-only"}) == "legacy-only"


def test_extract_tenant_id_returns_none_when_absent() -> None:
    assert extract_tenant_id({"sub": "u1"}) is None


def test_get_tenant_id_raises_401_when_missing() -> None:
    with pytest.raises(HTTPException) as excinfo:
        get_tenant_id({"sub": "u1"})
    assert excinfo.value.status_code == 401
    assert "tenant" in excinfo.value.detail.lower()


# ============================================================ JWT shape tests


def test_create_access_token_carries_both_claims() -> None:
    token = create_access_token(
        user_id="u-1", tenant_id="t-1", role="owner",
    )
    claims = decode_access_token(token)
    assert claims["tid"] == "t-1", "canonical `tid` must be present"
    assert claims["tenant_id"] == "t-1", "legacy `tenant_id` alias must be present"
    assert claims["sub"] == "u-1"
    assert claims["role"] == "owner"


# ============================================================== /me endpoint


@pytest.mark.asyncio
async def test_me_with_tid_only_token_succeeds(db_session) -> None:
    """Post-fix happy path: token has `tid` (current shape from login)."""
    tenant, user = await _seed_user(db_session, "me-tid-only")
    # `create_access_token` issues both — strip the legacy alias to
    # prove `tid` alone is sufficient.
    settings = get_settings()
    payload = {
        "sub": user.id,
        "tid": tenant.id,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.api_secret_key, algorithm=JWT_ALGORITHM)

    async for client in _client(db_session):
        resp = await client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["user_id"] == user.id
        assert body["tenant_id"] == tenant.id


@pytest.mark.asyncio
async def test_me_with_legacy_tenant_id_only_token_succeeds(db_session) -> None:
    """Backward-compat: tokens issued before the refactor still resolve."""
    tenant, user = await _seed_user(db_session, "me-legacy-only")
    token = _mint_legacy_token(user_id=user.id, tenant_id=tenant.id)

    async for client in _client(db_session):
        resp = await client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["user_id"] == user.id
        assert body["tenant_id"] == tenant.id


@pytest.mark.asyncio
async def test_me_without_any_tenant_claim_returns_401(db_session) -> None:
    """Token with neither `tid` nor `tenant_id` must be rejected."""
    _, user = await _seed_user(db_session, "me-no-claim")
    token = _mint_claimless_token(user_id=user.id)

    async for client in _client(db_session):
        resp = await client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401, resp.text
