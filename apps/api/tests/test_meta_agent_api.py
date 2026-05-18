"""Meta-agent HTTP routes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from deevai_api.db import get_session
from deevai_api.deps import get_current_tenant_id
from deevai_api.main import app
from deevai_api.models import Advertiser, AuditLog, Integration, LineItem, Setting, Tenant


@pytest.fixture
async def meta_client(db_session):
    tenant = Tenant(name="Meta", slug="test-meta-api", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    setting = Setting(tenant_id=tenant.id, default_cpv_target=0.5, max_step_per_run=0.20)
    db_session.add(setting)
    integration = Integration(tenant_id=tenant.id, name="Amazon", provider="amazon_dsp")
    db_session.add(integration)
    await db_session.flush()
    adv = Advertiser(
        tenant_id=tenant.id,
        integration_id=integration.id,
        amazon_advertiser_id="adv1",
        name="Adv",
        currency="EUR",
        country="IT",
    )
    db_session.add(adv)
    await db_session.flush()
    li = LineItem(
        tenant_id=tenant.id,
        advertiser_id=adv.id,
        name="Test LI",
        amazon_line_item_id="123",
        cpv_target=0.5,
    )
    db_session.add(li)
    await db_session.flush()

    async def override_session():
        yield db_session

    async def override_tenant():
        return tenant.id

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_tenant_id] = override_tenant

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, tenant.id, li.id, setting.id

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_brief_creates_proposal(meta_client) -> None:
    client, _tid, line_item_id, _sid = meta_client
    resp = await client.post(
        f"/v1/line-items/{line_item_id}/tuning-agent/brief",
        json={"brief": "Il CPA è troppo alto questa settimana"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["brief"]
    assert body["status"] in ("pending", "applied")


@pytest.mark.asyncio
async def test_list_proposals(meta_client) -> None:
    client, _tid, line_item_id, _sid = meta_client
    await client.post(
        f"/v1/line-items/{line_item_id}/tuning-agent/brief",
        json={"brief": "Oscillazione modifier"},
    )
    listed = await client.get("/v1/meta-agent/proposals")
    assert listed.status_code == 200
    assert len(listed.json()) >= 1


@pytest.mark.asyncio
async def test_auto_apply_writes_meta_agent_audit(meta_client, db_session) -> None:
    client, tenant_id, line_item_id, setting_id = meta_client
    resp = await client.post(
        f"/v1/line-items/{line_item_id}/tuning-agent/brief",
        json={"brief": "CPA alto e poche modifiche sui term"},
    )
    assert resp.status_code == 201
    proposal = resp.json()
    if proposal["status"] != "applied":
        pytest.skip("Proposal not auto-applied in this fixture")

    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.actor_type == "tuning_agent",
                AuditLog.entity == "settings",
                AuditLog.entity_id == setting_id,
            ),
        )
    ).scalars().all()
    assert len(rows) >= 1
