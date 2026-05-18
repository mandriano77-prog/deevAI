"""Pytest fixtures — async DB session against local Postgres."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from deevai_api.models import Base


def _resolve_test_database_url() -> str:
    if os.getenv("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "postgresql+asyncpg://deevai:deevai-dev-password@localhost:5432/deevai"


TEST_DATABASE_URL = _resolve_test_database_url()
if TEST_DATABASE_URL.startswith("postgresql://"):
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://", 1,
    )


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def api_client(db_session) -> AsyncIterator[tuple]:  # noqa: PT001
    """HTTP client with tenant override — shared by route tests."""
    import os
    from collections.abc import AsyncIterator as AI

    from httpx import ASGITransport, AsyncClient

    from deevai_api.db import get_session
    from deevai_api.deps import get_current_tenant_id
    from deevai_api.main import app
    from deevai_api.models import Tenant

    os.environ.setdefault("API_SECRET_KEY", "test-secret-key-32-chars-min!!")

    tenant = Tenant(name="API", slug="test-api-shared", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()

    async def override_session() -> AI:
        yield db_session

    async def override_tenant() -> str:
        return tenant.id

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_tenant_id] = override_tenant

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, tenant.id

    app.dependency_overrides.clear()
