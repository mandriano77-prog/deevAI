"""Action model + funnel helpers + REST routes (happy + validation per route)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from deevai_api.models import Action, Tenant
from deevai_api.services.actions import get_action_funnel, set_action_funnel


@pytest.mark.asyncio
async def test_action_create_read_funnel(db_session) -> None:
    tenant = Tenant(name="Demo", slug="test-actions", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()

    a1 = Action(tenant_id=tenant.id, name="visita_listing", type="visit", weight=1, value_eur=1)
    a2 = Action(
        tenant_id=tenant.id, name="richiesta_info", type="lead", weight=8, value_eur=7,
    )
    a3 = Action(
        tenant_id=tenant.id, name="appuntamento", type="lead", weight=30, value_eur=50,
    )
    db_session.add_all([a1, a2, a3])
    await db_session.flush()

    loaded = (
        await db_session.execute(
            select(Action).where(Action.tenant_id == tenant.id, Action.name == "visita_listing"),
        )
    ).scalar_one()
    assert loaded.weight == 1
    assert loaded.type == "visit"

    ordered = await set_action_funnel(
        db_session,
        tenant_id=tenant.id,
        ordered_action_ids=[a1.id, a2.id, a3.id],
    )
    assert len(ordered) == 3
    assert ordered[0].funnel_position == 1
    assert ordered[0].funnel_parent_id is None
    assert ordered[1].funnel_parent_id == a1.id
    assert ordered[2].funnel_parent_id == a2.id

    funnel = await get_action_funnel(db_session, tenant_id=tenant.id)
    assert [s.name for s in funnel] == ["visita_listing", "richiesta_info", "appuntamento"]


@pytest.mark.asyncio
async def test_funnel_rejects_unknown_action_id(db_session) -> None:
    tenant = Tenant(name="Demo", slug="test-funnel-err", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()

    with pytest.raises(Exception) as exc:
        await set_action_funnel(
            db_session,
            tenant_id=tenant.id,
            ordered_action_ids=["00000000-0000-0000-0000-000000000099"],
        )
    assert exc.value.status_code == 404  # type: ignore[attr-defined]


# --- HTTP: happy path + validation error per route ---


@pytest.mark.asyncio
async def test_get_actions_empty(api_client) -> None:
    client, _ = api_client
    resp = await client.get("/v1/actions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_post_actions_invalid_weight(api_client) -> None:
    client, _ = api_client
    resp = await client.post(
        "/v1/actions",
        json={"name": "bad", "type": "visit", "weight": -1, "value_eur": 1},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_actions_happy(api_client) -> None:
    client, _ = api_client
    resp = await client.post(
        "/v1/actions",
        json={"name": "step_a", "type": "visit", "weight": 1, "valueEur": 1},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "step_a"


@pytest.mark.asyncio
async def test_patch_action_not_found(api_client) -> None:
    client, _ = api_client
    resp = await client.patch(
        "/v1/actions/00000000-0000-0000-0000-000000000099",
        json={"name": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_action_happy(api_client) -> None:
    client, _ = api_client
    created = await client.post(
        "/v1/actions",
        json={"name": "patch_me", "type": "visit", "weight": 1, "value_eur": 1},
    )
    action_id = created.json()["id"]
    resp = await client.patch(f"/v1/actions/{action_id}", json={"weight": 2})
    assert resp.status_code == 200
    assert float(resp.json()["weight"]) == 2


@pytest.mark.asyncio
async def test_delete_action_not_found(api_client) -> None:
    client, _ = api_client
    resp = await client.delete("/v1/actions/00000000-0000-0000-0000-000000000099")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_action_soft_archive(api_client) -> None:
    client, _ = api_client
    created = await client.post(
        "/v1/actions",
        json={"name": "archive_me", "type": "visit", "weight": 1, "value_eur": 1},
    )
    action_id = created.json()["id"]
    resp = await client.delete(f"/v1/actions/{action_id}")
    assert resp.status_code == 204
    get_resp = await client.get("/v1/actions")
    assert all(a["id"] != action_id for a in get_resp.json())


@pytest.mark.asyncio
async def test_post_funnel_validation_empty(api_client) -> None:
    client, _ = api_client
    resp = await client.post("/v1/actions/funnel", json={"orderedActionIds": []})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_funnel_happy(api_client) -> None:
    client, _ = api_client
    ids: list[str] = []
    for name in ("f_a", "f_b"):
        r = await client.post(
            "/v1/actions",
            json={"name": name, "type": "visit", "weight": 1, "value_eur": 1},
        )
        ids.append(r.json()["id"])
    resp = await client.post("/v1/actions/funnel", json={"ordered_action_ids": ids})
    assert resp.status_code == 200
    assert resp.json()[1]["funnelParentId"] == ids[0]


@pytest.mark.asyncio
async def test_get_funnel_happy(api_client) -> None:
    client, _ = api_client
    r = await client.post(
        "/v1/actions",
        json={"name": "solo", "type": "visit", "weight": 1, "value_eur": 1},
    )
    aid = r.json()["id"]
    await client.post("/v1/actions/funnel", json={"ordered_action_ids": [aid]})
    resp = await client.get("/v1/actions/funnel")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
