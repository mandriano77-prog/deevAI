"""Audit log on settings PATCH."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from deevai_api.db import get_session
from deevai_api.deps import get_current_tenant_id
from deevai_api.main import app
from deevai_api.models import AuditLog, Setting, Tenant


@pytest.fixture
async def audit_client(db_session):
    tenant = Tenant(name="Audit", slug="test-audit", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    setting = Setting(tenant_id=tenant.id, default_cpv_target=0.50)
    db_session.add(setting)
    await db_session.flush()

    async def override_session():
        yield db_session

    async def override_tenant():
        return tenant.id

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_tenant_id] = override_tenant

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, tenant.id

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_settings_patch_writes_audit(audit_client, db_session) -> None:
    client, tenant_id = audit_client
    resp = await client.patch("/v1/settings", json={"max_step_per_run": 0.25})
    assert resp.status_code == 200

    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.entity == "settings",
            ),
        )
    ).scalars().all()
    assert len(rows) >= 1
    row = rows[-1]
    assert row.action == "update"
    assert row.before is not None
    assert row.after is not None
    assert row.before.get("max_step_per_run") != row.after.get("max_step_per_run")
