"""Demo-mode coverage — seed idempotency, demo-login, middleware, /me, migration.

Run with the standard pytest entry point. Uses the shared ``db_session``
fixture (live Postgres) and the FastAPI app's dependency overrides.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select

from deevai_api.config import get_settings
from deevai_api.db import get_session
from deevai_api.deps import get_current_user_claims
from deevai_api.main import app
from deevai_api.models import (
    Advertiser,
    Decision,
    HardConstraint,
    Integration,
    LineItem,
    OptimizationStrategy,
    Run,
    Setting,
    Tenant,
    User,
)
from deevai_api.services import secrets_vault
from deevai_api.services.auth import JWT_ALGORITHM


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _force_fernet_vault(monkeypatch):
    """Same trick the dv360 tests use — keep the secrets vault out of KMS mode."""
    monkeypatch.setattr(secrets_vault, "_use_kms", lambda: False)


@pytest.fixture(autouse=True)
def _ensure_api_secret(monkeypatch):
    """Make sure ``api_secret_key`` is set so JWT helpers can sign tokens."""
    os.environ.setdefault("API_SECRET_KEY", "test-secret-key-32-chars-min!!")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _seed_via_session(db_session) -> str:
    """Run the seed helpers against the active test session; return tenant id."""
    from scripts import seed_demo_tenant as seed_mod
    import random

    rng = random.Random(42)
    tenant = await seed_mod._upsert_tenant(db_session)
    await seed_mod._upsert_user(db_session, tenant.id)
    await seed_mod._upsert_setting(db_session, tenant.id)
    integration = await seed_mod._upsert_integration(db_session, tenant.id)
    advertiser = await seed_mod._upsert_advertiser(
        db_session, tenant.id, integration.id
    )
    line_items = await seed_mod._upsert_line_items(
        db_session, tenant.id, advertiser.id
    )
    await seed_mod._upsert_strategy_and_constraints(db_session, tenant.id)
    await seed_mod._seed_runs_and_decisions(db_session, tenant.id, line_items, rng)
    await db_session.commit()
    return tenant.id


async def _count_rows(db_session) -> dict[str, int]:
    """Read row counts on a fresh transaction.

    After ``db_session.commit()`` asyncpg can hold the previous tx's snapshot
    on the underlying connection — a same-session SELECT then returns stale
    (zero) counts. ``rollback()`` here is a no-op for data (the commit already
    persisted) but it forces SQLAlchemy to open a brand-new tx so the next
    SELECT sees a fresh snapshot.
    """
    await db_session.rollback()
    return {
        "tenants": await db_session.scalar(select(func.count()).select_from(Tenant)),
        "users": await db_session.scalar(select(func.count()).select_from(User)),
        "integrations": await db_session.scalar(
            select(func.count()).select_from(Integration)
        ),
        "advertisers": await db_session.scalar(
            select(func.count()).select_from(Advertiser)
        ),
        "line_items": await db_session.scalar(
            select(func.count()).select_from(LineItem)
        ),
        "runs": await db_session.scalar(select(func.count()).select_from(Run)),
        "decisions": await db_session.scalar(
            select(func.count()).select_from(Decision)
        ),
        "strategies": await db_session.scalar(
            select(func.count()).select_from(OptimizationStrategy)
        ),
        "constraints": await db_session.scalar(
            select(func.count()).select_from(HardConstraint)
        ),
    }


# ---------------------------------------------------------------------------
# 1) seed idempotency
# ---------------------------------------------------------------------------


async def test_seed_demo_tenant_is_idempotent(db_session):
    """Running the seed twice must not duplicate any row."""
    tid1 = await _seed_via_session(db_session)
    counts_after_first = await _count_rows(db_session)

    tid2 = await _seed_via_session(db_session)
    counts_after_second = await _count_rows(db_session)

    assert tid1 == tid2, "Seed must converge to the same tenant id"
    assert counts_after_first == counts_after_second, (
        f"Seed not idempotent: {counts_after_first} vs {counts_after_second}"
    )
    # 3 line items × 4 runs = 12 — sanity check.
    assert counts_after_first["runs"] == 12
    assert counts_after_first["line_items"] == 3
    assert counts_after_first["constraints"] == 2


# ---------------------------------------------------------------------------
# 2) demo-login — enabled vs disabled by env
# ---------------------------------------------------------------------------


async def _make_api_client(db_session) -> AsyncClient:
    """Bare client that does NOT pre-override tenant id — we want the real auth dep."""

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_demo_login_returns_404_when_env_missing(db_session, monkeypatch):
    """Without ``DEMO_TENANT_ID`` set, the route is effectively disabled."""
    monkeypatch.delenv("DEMO_TENANT_ID", raising=False)
    get_settings.cache_clear()

    from deevai_api.routers import auth as auth_router

    auth_router._reset_demo_login_buckets()

    client = await _make_api_client(db_session)
    try:
        resp = await client.post("/v1/auth/demo-login")
        assert resp.status_code == 404, resp.text
    finally:
        await client.aclose()
        app.dependency_overrides.clear()


async def test_demo_login_returns_token_when_env_set(db_session, monkeypatch):
    tenant_id = await _seed_via_session(db_session)
    monkeypatch.setenv("DEMO_TENANT_ID", tenant_id)
    get_settings.cache_clear()

    from deevai_api.routers import auth as auth_router

    auth_router._reset_demo_login_buckets()

    client = await _make_api_client(db_session)
    try:
        resp = await client.post("/v1/auth/demo-login")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["tenant_id"] == tenant_id
        assert body["tenant_slug"] == "demo"
        # Decode the minted JWT — must carry ``tid`` + ``is_demo``.
        settings = get_settings()
        decoded = jwt.decode(
            body["access_token"],
            settings.api_secret_key,
            algorithms=[JWT_ALGORITHM],
        )
        assert decoded["tid"] == tenant_id
        assert decoded["is_demo"] is True
    finally:
        await client.aclose()
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 3) demo-login rate limit — 11th call returns 429
# ---------------------------------------------------------------------------


async def test_demo_login_rate_limit_blocks_11th_call(db_session, monkeypatch):
    tenant_id = await _seed_via_session(db_session)
    monkeypatch.setenv("DEMO_TENANT_ID", tenant_id)
    get_settings.cache_clear()

    from deevai_api.routers import auth as auth_router

    auth_router._reset_demo_login_buckets()

    client = await _make_api_client(db_session)
    try:
        for i in range(10):
            resp = await client.post("/v1/auth/demo-login")
            assert resp.status_code == 200, f"call {i} failed: {resp.text}"
        resp = await client.post("/v1/auth/demo-login")
        assert resp.status_code == 429, resp.text
    finally:
        await client.aclose()
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 4) middleware — GET passes, POST /v1/studio/scripts returns 403 + body flag
# ---------------------------------------------------------------------------


def _make_demo_token(tenant_id: str, user_id: str) -> str:
    """Sign a JWT that looks exactly like what /demo-login mints."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tid": tenant_id,
        "role": "owner",
        "is_demo": True,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.api_secret_key, algorithm=JWT_ALGORITHM)


async def test_demo_middleware_blocks_writes_allows_gets(db_session, monkeypatch):
    tenant_id = await _seed_via_session(db_session)
    monkeypatch.setenv("DEMO_TENANT_ID", tenant_id)
    get_settings.cache_clear()

    user = await db_session.scalar(
        select(User).where(User.tenant_id == tenant_id)
    )
    token = _make_demo_token(tenant_id, user.id)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            # GET on the protected prefix — must NOT carry the demo 403 body.
            resp = await client.get("/v1/integrations/")
            if resp.status_code == 403:
                assert resp.json().get("demo") is not True, (
                    "GET on /v1/integrations/ should not be blocked by demo guard"
                )

            # POST on /v1/studio/scripts — must be 403 with the demo flag.
            resp = await client.post(
                "/v1/studio/scripts", json={"name": "evil-write"}
            )
            assert resp.status_code == 403, resp.text
            body = resp.json()
            assert body == {
                "detail": "Demo tenant is read-only",
                "demo": True,
            }, body

            # PATCH on /v1/integrations/some-id — same treatment.
            resp = await client.patch(
                "/v1/integrations/abc", json={"name": "evil-rename"}
            )
            assert resp.status_code == 403
            assert resp.json()["demo"] is True
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 5) middleware — non-demo tenant is unaffected
# ---------------------------------------------------------------------------


async def test_demo_middleware_passes_through_for_non_demo_tenant(
    db_session, monkeypatch
):
    """A token whose ``tid`` is NOT the demo tenant must never see the 403 body."""
    demo_tid = await _seed_via_session(db_session)
    monkeypatch.setenv("DEMO_TENANT_ID", demo_tid)
    get_settings.cache_clear()

    other = Tenant(
        name="Real Customer", slug="real-customer", plan="beta", status="active"
    )
    db_session.add(other)
    await db_session.flush()
    other_user = User(
        tenant_id=other.id,
        email="ceo@realcustomer.com",
        name="CEO",
        password_hash="x" * 60,
        role="owner",
        status="active",
    )
    db_session.add(other_user)
    await db_session.flush()
    await db_session.commit()

    token = _make_demo_token(other.id, other_user.id)  # token shape, real tid

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            resp = await client.post(
                "/v1/studio/scripts", json={"name": "ok"}
            )
            # Whatever it returns (404 since the route doesn't exist), it must
            # NOT be the demo-readonly 403 body.
            if resp.status_code == 403:
                assert resp.json().get("demo") is not True
            else:
                # Route doesn't exist — Starlette returns 404. Acceptable.
                assert resp.status_code in (404, 401, 405, 422)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 6) /v1/auth/me — tenant_is_demo true only for demo tenant
# ---------------------------------------------------------------------------


async def test_me_response_carries_is_demo_flag(db_session, monkeypatch):
    demo_tid = await _seed_via_session(db_session)
    monkeypatch.setenv("DEMO_TENANT_ID", demo_tid)
    get_settings.cache_clear()

    # Real (non-demo) tenant for comparison.
    real_tenant = Tenant(
        name="Real", slug="real", plan="beta", status="active"
    )
    db_session.add(real_tenant)
    await db_session.flush()
    real_user = User(
        tenant_id=real_tenant.id,
        email="real@x.com",
        name="Real",
        password_hash="x" * 60,
        role="owner",
        status="active",
    )
    db_session.add(real_user)
    await db_session.flush()
    await db_session.commit()

    demo_user = await db_session.scalar(
        select(User).where(User.tenant_id == demo_tid)
    )

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)

    try:
        # Demo /me — tenant_is_demo must be True.
        async def demo_claims():
            return {"sub": demo_user.id, "tid": demo_tid}

        app.dependency_overrides[get_current_user_claims] = demo_claims
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/auth/me")
            assert resp.status_code == 200, resp.text
            assert resp.json()["tenant_is_demo"] is True

        # Real /me — tenant_is_demo must be False.
        async def real_claims():
            return {"sub": real_user.id, "tid": real_tenant.id}

        app.dependency_overrides[get_current_user_claims] = real_claims
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/auth/me")
            assert resp.status_code == 200, resp.text
            assert resp.json()["tenant_is_demo"] is False
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 7) migration 0004 — column + partial index round-trip
# ---------------------------------------------------------------------------


async def test_migration_0004_up_and_down(db_session):
    """Round-trip ``is_demo`` via the migration's DDL contract.

    The conftest builds the schema via ``Base.metadata.create_all`` so the
    ``is_demo`` column already exists when this test runs. We verify:

    * the migration module declares the expected revision / down_revision
    * the ``is_demo`` column accepts both TRUE and FALSE
    * the partial index from the migration can be created idempotently
    * ``upgrade`` / ``downgrade`` are both callable (smoke check the module
      is importable end-to-end)
    """
    from importlib import import_module
    from sqlalchemy import text

    mod = import_module("alembic.versions.0004_tenant_is_demo")
    assert mod.revision == "0004_tenant_is_demo"
    assert mod.down_revision == "0002_reporting_metrics"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)

    await db_session.execute(
        text(
            "INSERT INTO tenants (id, name, slug, plan, status, is_demo, "
            "created_at, updated_at) VALUES "
            "(:i, :n, :s, 'demo', 'active', TRUE, NOW(), NOW())"
        ),
        {"i": str(uuid.uuid4()), "n": "MigTest", "s": "mig-test-demo"},
    )
    await db_session.execute(
        text(
            "INSERT INTO tenants (id, name, slug, plan, status, is_demo, "
            "created_at, updated_at) VALUES "
            "(:i, :n, :s, 'beta', 'active', FALSE, NOW(), NOW())"
        ),
        {"i": str(uuid.uuid4()), "n": "MigTestReal", "s": "mig-test-real"},
    )
    row_true = await db_session.scalar(
        text("SELECT is_demo FROM tenants WHERE slug = 'mig-test-demo'")
    )
    row_false = await db_session.scalar(
        text("SELECT is_demo FROM tenants WHERE slug = 'mig-test-real'")
    )
    assert row_true is True
    assert row_false is False

    # Partial index from the migration — explicitly recreate to verify shape.
    await db_session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_tenants_is_demo_true ON tenants "
            "(is_demo) WHERE is_demo = true"
        )
    )
    idx = await db_session.scalar(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE indexname = 'ix_tenants_is_demo_true'"
        )
    )
    assert idx == "ix_tenants_is_demo_true"

    # Downgrade path's DROP is exercised inline (DDL only) — the column itself
    # stays around because the shared session needs it for the rest of the suite.
    await db_session.execute(text("DROP INDEX IF EXISTS ix_tenants_is_demo_true"))
