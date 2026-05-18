"""M.AI HTTP routes."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from deevai_api.db import get_session
from deevai_api.deps import get_current_tenant_id
from deevai_api.main import app
from deevai_api.models import Advertiser, Integration, LineItem, Tenant
from deevai_api.services.mai import rate_limit


@pytest.fixture
async def mai_api_client(db_session):
    tenant = Tenant(name="MAI", slug="test-mai", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    integration = Integration(tenant_id=tenant.id, name="Amazon", provider="amazon_dsp")
    db_session.add(integration)
    await db_session.flush()
    adv = Advertiser(
        tenant_id=tenant.id,
        integration_id=integration.id,
        amazon_advertiser_id="adv-mai",
        name="Adv",
        currency="EUR",
        country="IT",
    )
    db_session.add(adv)
    await db_session.flush()
    li = LineItem(
        tenant_id=tenant.id,
        advertiser_id=adv.id,
        name="MAI LI",
        amazon_line_item_id="li-mai",
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
    rate_limit.reset_mai_rate_limit_for_tests()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, tenant.id, li.id

    app.dependency_overrides.clear()
    rate_limit.reset_mai_rate_limit_for_tests()


def _valid_llm_payload(intent: str, typ: str) -> dict:
    base = {
        "intent": intent,
        "type": typ,
        "preview": {"summary": "Test", "details": {}, "warnings": []},
    }
    if typ in ("brief", "govern"):
        base["payload"] = {"proposal_id": "x"} if typ == "govern" else {"line_item_id": "y", "brief": "z"}
    else:
        base["payload"] = None
        base["answer"] = "Ok"
    return base


@pytest.mark.asyncio
async def test_execute_rejects_unknown_intent(mai_api_client) -> None:
    client, _tid, _li = mai_api_client
    resp = await client.post("/v1/mai/execute", json={"intent": "tenant.delete", "payload": {}})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_wrong_line_item_404_on_ask(mai_api_client) -> None:
    client, _tid, _li = mai_api_client
    fake_id = "00000000-0000-4000-8000-000000000099"
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    payload = _valid_llm_payload("dashboard.read", "query")
    with patch(
        "deevai_api.routers.mai.call_mai",
        new_callable=AsyncMock,
        return_value={"parsed": payload, "input_tokens": 1, "output_tokens": 2},
    ):
        resp = await client.post(
            "/v1/mai/ask",
            json={"prompt": "Status?", "lineItemId": fake_id},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ask_invalid_json_502(mai_api_client) -> None:
    client, _tid, li = mai_api_client
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    with patch(
        "deevai_api.routers.mai.call_mai",
        new_callable=AsyncMock,
        side_effect=ValueError("bad json"),
    ):
        resp = await client.post(
            "/v1/mai/ask",
            json={"prompt": "Ciao", "lineItemId": li},
        )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_rate_limit_429(mai_api_client, monkeypatch) -> None:
    client, _tid, li = mai_api_client
    monkeypatch.setattr(rate_limit, "MAX_REQUESTS", 2)
    rate_limit.reset_mai_rate_limit_for_tests()
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    payload = _valid_llm_payload("dashboard.read", "query")
    with patch(
        "deevai_api.routers.mai.call_mai",
        new_callable=AsyncMock,
        return_value={"parsed": payload, "input_tokens": 1, "output_tokens": 2},
    ):
        assert (await client.post("/v1/mai/ask", json={"prompt": "a", "lineItemId": li})).status_code == 200
        assert (await client.post("/v1/mai/ask", json={"prompt": "b", "lineItemId": li})).status_code == 200
        resp = await client.post("/v1/mai/ask", json={"prompt": "c", "lineItemId": li})
    assert resp.status_code == 429
    rate_limit.reset_mai_rate_limit_for_tests()


@pytest.mark.asyncio
async def test_dashboard_query_uses_db_reader(mai_api_client) -> None:
    client, _tid, li = mai_api_client
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    payload = _valid_llm_payload("dashboard.read", "query")
    payload["payload"] = None
    payload["answer"] = "placeholder"
    with patch(
        "deevai_api.routers.mai.call_mai",
        new_callable=AsyncMock,
        return_value={"parsed": payload, "input_tokens": 5, "output_tokens": 10},
    ):
        resp = await client.post(
            "/v1/mai/ask",
            json={"prompt": "Come va la campagna?", "lineItemId": li},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "dashboard.read"
    assert "MAI LI" in (body.get("answer") or "")


@pytest.mark.asyncio
async def test_help_intent_enriched(mai_api_client) -> None:
    client, _tid, li = mai_api_client
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    payload = _valid_llm_payload("help", "system")
    payload["payload"] = None
    with patch(
        "deevai_api.routers.mai.call_mai",
        new_callable=AsyncMock,
        return_value={"parsed": payload, "input_tokens": 1, "output_tokens": 1},
    ):
        resp = await client.post(
            "/v1/mai/ask",
            json={"prompt": "Cosa puoi fare?", "lineItemId": li},
        )
    assert resp.status_code == 200
    assert "Setup Agent" in resp.json().get("answer", "")


@pytest.mark.asyncio
async def test_history_returns_logs(mai_api_client, monkeypatch) -> None:
    client, _tid, li = mai_api_client
    monkeypatch.setattr(rate_limit, "MAX_REQUESTS", 100)
    rate_limit.reset_mai_rate_limit_for_tests()
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    payload = _valid_llm_payload("dashboard.read", "query")
    with patch(
        "deevai_api.routers.mai.call_mai",
        new_callable=AsyncMock,
        return_value={"parsed": payload, "input_tokens": 10, "output_tokens": 20},
    ):
        await client.post("/v1/mai/ask", json={"prompt": "Come va?", "lineItemId": li})

    hist = await client.get("/v1/mai/history", params={"lineItemId": li, "limit": 5})
    assert hist.status_code == 200
    body = hist.json()
    assert "items" in body
    assert len(body["items"]) >= 1
