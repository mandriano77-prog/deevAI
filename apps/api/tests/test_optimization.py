"""Optimization strategy + hard constraint — service + REST per route."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from deevai_api.models import AuditLog, HardConstraint, OptimizationStrategy, Tenant
from deevai_api.schemas.hard_constraint import HardConstraintCreate


@pytest.mark.asyncio
async def test_line_item_without_strategy_uses_legacy_path(db_session) -> None:
    tenant = Tenant(name="Demo", slug="test-opt-legacy", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()

    from deevai_api.services.optimization import get_strategy_for_scope

    strategy = await get_strategy_for_scope(
        db_session, tenant_id=tenant.id, line_item_id="nonexistent-li",
    )
    assert strategy is None


@pytest.mark.asyncio
async def test_tenant_default_strategy(db_session) -> None:
    tenant = Tenant(name="Demo", slug="test-opt-default", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()

    strategy = OptimizationStrategy(
        tenant_id=tenant.id,
        mode="blended_2",
        primary_metric="cpa",
        primary_target=4.5,
        primary_weight=70,
        secondary_metric="cpc",
        secondary_target=0.1,
        secondary_weight=30,
    )
    db_session.add(strategy)
    await db_session.flush()

    from deevai_api.services.optimization import get_strategy_for_scope

    loaded = await get_strategy_for_scope(
        db_session, tenant_id=tenant.id, line_item_id=None,
    )
    assert loaded is not None
    assert loaded.mode == "blended_2"
    assert loaded.primary_metric == "cpa"


def test_blended_weights_sum_99_returns_422() -> None:
    from deevai_api.schemas.optimization_strategy import OptimizationStrategyCreate
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OptimizationStrategyCreate(
            mode="blended_2",
            primary_metric="cpa",
            primary_target=4.5,
            primary_weight=70,
            secondary_metric="cpc",
            secondary_target=0.1,
            secondary_weight=29,
        )


def test_constraint_cpc_gte_rejected() -> None:
    with pytest.raises(ValidationError):
        HardConstraintCreate(metric="cpc", operator="gte", value=0.10)


@pytest.mark.asyncio
async def test_constraint_seed_metrics(db_session) -> None:
    tenant = Tenant(name="Demo", slug="test-opt-constraints", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()

    strategy = OptimizationStrategy(
        tenant_id=tenant.id,
        mode="blended_2",
        primary_metric="cpa",
        primary_target=4.5,
        primary_weight=70,
        secondary_metric="cpc",
        secondary_target=0.1,
        secondary_weight=30,
    )
    db_session.add(strategy)
    await db_session.flush()

    rows = [
        HardConstraintCreate(metric="cpc", operator="lte", value=0.15),
        HardConstraintCreate(metric="viewability", operator="gte", value=0.50),
        HardConstraintCreate(metric="fraud_rate", operator="lte", value=0.015),
    ]
    for spec in rows:
        db_session.add(
            HardConstraint(
                tenant_id=tenant.id,
                optimization_strategy_id=strategy.id,
                **spec.model_dump(),
            ),
        )
    await db_session.flush()

    from deevai_api.services.optimization import list_constraints

    constraints = await list_constraints(
        db_session, tenant_id=tenant.id, strategy_id=strategy.id,
    )
    assert len(constraints) == 3


# --- HTTP: happy + validation per route ---


@pytest.fixture
async def opt_client(api_client, db_session):
    client, tenant_id = api_client
    strategy = OptimizationStrategy(
        tenant_id=tenant_id,
        mode="blended_2",
        primary_metric="cpa",
        primary_target=4.5,
        primary_weight=70,
        secondary_metric="cpc",
        secondary_target=0.1,
        secondary_weight=30,
    )
    db_session.add(strategy)
    await db_session.flush()
    yield client, tenant_id, strategy.id


@pytest.mark.asyncio
async def test_get_strategy_404(api_client) -> None:
    client, _ = api_client
    resp = await client.get("/v1/optimization-strategies/default")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_strategy_happy(opt_client) -> None:
    client, _tid, _sid = opt_client
    resp = await client.get("/v1/optimization-strategies/default")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "blended_2"


@pytest.mark.asyncio
async def test_put_strategy_validation_tolerance(opt_client) -> None:
    client, _tid, _sid = opt_client
    resp = await client.put(
        "/v1/optimization-strategies/default",
        json={
            "mode": "single",
            "primaryMetric": "cpv",
            "primaryTarget": 0.5,
            "primaryWeight": 100,
            "toleranceBand": 0.9,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_strategy_happy(opt_client) -> None:
    client, _tid, _sid = opt_client
    resp = await client.put(
        "/v1/optimization-strategies/default",
        json={
            "mode": "single",
            "primary_metric": "cpv",
            "primary_target": 0.55,
            "primary_weight": 100,
            "tolerance_band": 0.2,
        },
    )
    assert resp.status_code == 200
    assert float(resp.json()["primaryTarget"]) == 0.55


@pytest.mark.asyncio
async def test_delete_strategy_404(api_client) -> None:
    client, _ = api_client
    resp = await client.delete("/v1/optimization-strategies/default")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_strategy_happy(opt_client) -> None:
    client, _tid, _sid = opt_client
    resp = await client.delete("/v1/optimization-strategies/default")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_list_constraints_happy(opt_client) -> None:
    client, _tid, sid = opt_client
    await client.post(
        f"/v1/optimization-strategies/{sid}/constraints",
        json={"metric": "cpc", "operator": "lte", "value": 0.15},
    )
    resp = await client.get(f"/v1/optimization-strategies/{sid}/constraints")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_post_constraint_validation_cpc_gte(opt_client) -> None:
    client, _tid, sid = opt_client
    resp = await client.post(
        f"/v1/optimization-strategies/{sid}/constraints",
        json={"metric": "cpc", "operator": "gte", "value": 0.1},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_constraint_happy(opt_client) -> None:
    client, _tid, sid = opt_client
    resp = await client.post(
        f"/v1/optimization-strategies/{sid}/constraints",
        json={
            "metric": "viewability",
            "operator": "gte",
            "value": 0.5,
            "violationPolicy": "throttle",
        },
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_patch_constraint_404(api_client) -> None:
    client, _ = api_client
    resp = await client.patch(
        "/v1/constraints/00000000-0000-0000-0000-000000000099",
        json={"value": 0.2},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_constraint_validation(opt_client) -> None:
    client, _tid, sid = opt_client
    created = await client.post(
        f"/v1/optimization-strategies/{sid}/constraints",
        json={"metric": "cpc", "operator": "lte", "value": 0.12},
    )
    cid = created.json()["id"]
    resp = await client.patch(
        f"/v1/constraints/{cid}",
        json={"operator": "gte"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_constraint_happy(opt_client) -> None:
    client, _tid, sid = opt_client
    created = await client.post(
        f"/v1/optimization-strategies/{sid}/constraints",
        json={"metric": "cpc", "operator": "lte", "value": 0.12},
    )
    cid = created.json()["id"]
    resp = await client.patch(f"/v1/constraints/{cid}", json={"value": 0.14})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_constraint_404(api_client) -> None:
    client, _ = api_client
    resp = await client.delete("/v1/constraints/00000000-0000-0000-0000-000000000099")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_constraint_happy(opt_client) -> None:
    client, _tid, sid = opt_client
    created = await client.post(
        f"/v1/optimization-strategies/{sid}/constraints",
        json={"metric": "fraud_rate", "operator": "lte", "value": 0.02},
    )
    cid = created.json()["id"]
    resp = await client.delete(f"/v1/constraints/{cid}")
    assert resp.status_code == 204
