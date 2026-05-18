"""Setup Agent — validation, apply batch, mocked brief pipeline."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from deevai_api.db import get_session
from deevai_api.deps import get_current_tenant_id
from deevai_api.main import app
from deevai_api.models import (
    Advertiser,
    AgentProposal,
    AuditLog,
    Integration,
    LineItem,
    OptimizationStrategy,
    Setting,
    Tenant,
)
from deevai_api.services.setup_agent.applier import apply_proposal
from deevai_api.services.setup_agent.validate import validate_changes


@pytest.fixture
async def setup_fixture(db_session):
    tenant = Tenant(name="Setup", slug="test-setup-agent", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    setting = Setting(tenant_id=tenant.id, default_cpv_target=0.5, max_step_per_run=0.30)
    db_session.add(setting)
    integration = Integration(tenant_id=tenant.id, name="Amazon", provider="amazon_dsp")
    db_session.add(integration)
    await db_session.flush()
    adv = Advertiser(
        tenant_id=tenant.id,
        integration_id=integration.id,
        amazon_advertiser_id="adv-setup",
        name="Adv",
        currency="EUR",
        country="IT",
    )
    db_session.add(adv)
    await db_session.flush()
    li = LineItem(
        tenant_id=tenant.id,
        advertiser_id=adv.id,
        name="Setup LI",
        amazon_line_item_id="li-setup",
        cpv_target=0.55,
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


def test_validate_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_changes([])


def test_validate_accepts_create_payload() -> None:
    validate_changes([
        {
            "entity": "optimization_strategy",
            "operation": "create",
            "payload": {"mode": "single", "primary_metric": "cpv", "primary_target": 0.5},
        },
    ])


@pytest.mark.asyncio
async def test_apply_setup_creates_strategy_actions_constraints(
    db_session, setup_fixture,
) -> None:
    _client, tenant_id, line_item_id, setting_id = setup_fixture
    changes = [
        {
            "entity": "optimization_strategy",
            "operation": "create",
            "payload": {
                "line_item_id": line_item_id,
                "mode": "blended_2",
                "primary_metric": "cpa",
                "primary_target": 4.5,
                "primary_weight": 70,
                "secondary_metric": "cpc",
                "secondary_target": 0.12,
                "secondary_weight": 30,
                "tolerance_band": 0.2,
            },
        },
        {
            "entity": "action",
            "operation": "create",
            "payload": {"name": "Visit", "type": "visit", "weight": 1.0, "value_eur": 1.0},
        },
        {
            "entity": "action",
            "operation": "create",
            "payload": {
                "name": "Purchase",
                "type": "purchase",
                "weight": 1.0,
                "value_eur": 40.0,
                "funnel_parent_name": "Visit",
            },
        },
        {
            "entity": "hard_constraint",
            "operation": "create",
            "payload": {
                "metric": "cpc",
                "operator": "lte",
                "value": 0.2,
                "violation_policy": "throttle",
            },
        },
        {
            "entity": "settings",
            "operation": "update",
            "entity_id": setting_id,
            "payload": {"max_step_per_run": 0.25},
        },
    ]
    proposal = AgentProposal(
        tenant_id=tenant_id,
        agent_type="setup",
        line_item_id=line_item_id,
        brief="Configura blended CPA+CPC",
        diagnosis="Setup test",
        proposed_changes=changes,
        status="approved",
        auto_applicable=False,
    )
    db_session.add(proposal)
    await db_session.flush()

    await apply_proposal(db_session, proposal_id=proposal.id, user_id=None)
    await db_session.commit()

    strategies = (
        await db_session.execute(
            select(OptimizationStrategy).where(
                OptimizationStrategy.tenant_id == tenant_id,
                OptimizationStrategy.line_item_id == line_item_id,
            ),
        )
    ).scalars().all()
    assert len(strategies) == 1
    assert strategies[0].mode == "blended_2"

    audits = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.proposal_id == proposal.id,
            ),
        )
    ).scalars().all()
    assert len(audits) >= 4
    assert {a.actor_type for a in audits} == {"setup_agent"}


@pytest.mark.asyncio
async def test_setup_brief_mocked_llm(setup_fixture) -> None:
    client, _tenant_id, line_item_id, _setting_id = setup_fixture
    llm_payload = {
        "diagnosis": "Configurazione iniziale consigliata",
        "proposed_changes": [
            {
                "entity": "optimization_strategy",
                "operation": "create",
                "payload": {
                    "mode": "single",
                    "primary_metric": "cpv",
                    "primary_target": 0.55,
                    "primary_weight": 100,
                },
            },
        ],
        "expected_impact": {"confidence": "high"},
    }
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(llm_payload))]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=200)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = mock_response
            resp = await client.post(
                f"/v1/line-items/{line_item_id}/setup-agent/brief",
                json={"brief": "Voglio ottimizzare CPV a 0.55"},
            )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["agentType"] == "setup"
    assert body["status"] == "pending"
    assert len(body["proposedChanges"]) >= 1
