"""Scheduler bridge: legacy CPV vs multi-objective strategy."""

from __future__ import annotations

import pytest

from deevai_api.models import (
    HardConstraint,
    LineItem,
    OptimizationStrategy,
    Setting,
    Tenant,
    Advertiser,
    Integration,
)
from deevai_api.services.bidagent_runtime import build_line_item_plan
from bidagent.providers.dv360.mock_data import (
    fake_dv360_week_metrics,
    fake_current_bid_multipliers,
    fake_runs_since_zeroed,
    filter_supported_metrics,
)


async def _line_item_setup(db_session):
    tenant = Tenant(name="Runtime", slug="test-runtime", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    setting = Setting(tenant_id=tenant.id, default_cpv_target=0.5)
    integration = Integration(tenant_id=tenant.id, name="Amazon", provider="amazon_dsp")
    db_session.add(integration)
    await db_session.flush()
    adv = Advertiser(
        tenant_id=tenant.id,
        integration_id=integration.id,
        amazon_advertiser_id="a1",
        name="Adv",
        currency="EUR",
        country="IT",
    )
    db_session.add(adv)
    await db_session.flush()
    li = LineItem(
        tenant_id=tenant.id,
        advertiser_id=adv.id,
        name="LI",
        amazon_line_item_id="99",
        cpv_target=0.5,
    )
    db_session.add(li)
    await db_session.flush()
    return tenant, setting, li


@pytest.mark.asyncio
async def test_no_strategy_uses_legacy_cpv_path(db_session) -> None:
    tenant, setting, li = await _line_item_setup(db_session)
    metrics = filter_supported_metrics(fake_dv360_week_metrics())
    plan = await build_line_item_plan(
        db_session,
        tenant_id=tenant.id,
        line_item=li,
        setting=setting,
        metrics=metrics,
        current_modifiers=fake_current_bid_multipliers(metrics),
        runs_since_zeroed=fake_runs_since_zeroed(),
        current_max_bid=5.0,
        week_label="2026-W01",
    )
    assert plan.decisions


@pytest.mark.asyncio
async def test_blended_cpa_strategy_changes_path(db_session) -> None:
    tenant, setting, li = await _line_item_setup(db_session)
    strategy = OptimizationStrategy(
        tenant_id=tenant.id,
        mode="blended_2",
        primary_metric="cpa",
        primary_target=4.5,
        primary_weight=70,
        secondary_metric="cpc",
        secondary_target=0.10,
        secondary_weight=30,
    )
    db_session.add(strategy)
    await db_session.flush()

    metrics = filter_supported_metrics(fake_dv360_week_metrics())
    plan = await build_line_item_plan(
        db_session,
        tenant_id=tenant.id,
        line_item=li,
        setting=setting,
        metrics=metrics,
        current_modifiers=fake_current_bid_multipliers(metrics),
        runs_since_zeroed=fake_runs_since_zeroed(),
        current_max_bid=5.0,
        week_label="2026-W01",
    )
    assert plan.decisions
    assert any(d.note and "blended_score" in d.note for d in plan.decisions)
