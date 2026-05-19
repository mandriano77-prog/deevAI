"""Reporting layer — service + REST routes.

The reporting layer is read-only: we never mutate state here. These
tests cover the four routes plus the underlying service helpers.

Tenant scoping is enforced via the JWT claims dependency. The fixture
``api_client`` overrides only ``get_current_tenant_id``; for reporting
we override ``get_current_user_claims`` per test so we can simulate
both same-tenant and cross-tenant access without minting real JWTs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator as AI

import pytest
from httpx import ASGITransport, AsyncClient

from deevai_api.db import get_session
from deevai_api.deps import get_current_user_claims
from deevai_api.main import app
from deevai_api.models import Advertiser, Decision, Integration, LineItem, Run, Tenant


# ----------------------------------------------------------------- helpers


async def _make_world(
    db_session,
    *,
    tenant_slug: str,
    week_label: str = "2026-W20",
) -> tuple[Tenant, LineItem, Run]:
    """Set up a tenant + advertiser + line item + a single succeeded run."""
    tenant = Tenant(
        name=f"T-{tenant_slug}", slug=tenant_slug, plan="beta", status="active",
    )
    db_session.add(tenant)
    await db_session.flush()

    integration = Integration(
        tenant_id=tenant.id,
        provider="dv360",
        name="Default Integration",
        status="connected",
    )
    db_session.add(integration)
    await db_session.flush()

    advertiser = Advertiser(
        tenant_id=tenant.id,
        integration_id=integration.id,
        amazon_advertiser_id="adv-001",
        name="Acme",
    )
    db_session.add(advertiser)
    await db_session.flush()

    line_item = LineItem(
        tenant_id=tenant.id,
        advertiser_id=advertiser.id,
        amazon_line_item_id="dsp-li-1",
        name="LI #1",
        cpv_target=0.50,
    )
    db_session.add(line_item)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    run = Run(
        tenant_id=tenant.id,
        line_item_id=line_item.id,
        week_label=week_label,
        window_start=now - timedelta(days=7),
        window_end=now,
        status="succeeded",
        started_at=now - timedelta(minutes=5),
        completed_at=now,
        blended_cpv_target=0.50,
        blended_cpv_observed=0.42,
        blended_impressions=200_000,
        blended_clicks=2_000,
        blended_visits=400,
        blended_spend=600.00,
        blended_roas=1.5,
        n_decisions=5,
        n_changes_proposed=4,
        n_changes_applied=0,
    )
    db_session.add(run)
    await db_session.flush()

    return tenant, line_item, run


def _override_claims(tenant_id: str) -> None:
    """Force the reporting routes to see ``tenant_id`` via JWT claims."""
    async def fake_claims() -> dict:
        return {"sub": "test-user", "tid": tenant_id, "role": "owner"}

    app.dependency_overrides[get_current_user_claims] = fake_claims


async def _client(db_session) -> AsyncIterator:
    async def override_session() -> AI:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================ service tests


@pytest.mark.asyncio
async def test_get_run_summary_happy_path(db_session) -> None:
    from deevai_api.services.reporting import get_run_summary

    tenant, line_item, run = await _make_world(db_session, tenant_slug="rep-summary-ok")

    # Add a handful of decisions so live distribution kicks in.
    db_session.add_all(
        [
            Decision(
                tenant_id=tenant.id,
                run_id=run.id,
                targeting_module="device",
                targeting_key="type",
                value="mobile",
                previous_modifier=1.00,
                new_modifier=1.20,
                reason="under_target",
            ),
            Decision(
                tenant_id=tenant.id,
                run_id=run.id,
                targeting_module="device",
                targeting_key="type",
                value="desktop",
                previous_modifier=1.00,
                new_modifier=0.80,
                reason="over_target",
            ),
            Decision(
                tenant_id=tenant.id,
                run_id=run.id,
                targeting_module="device",
                targeting_key="type",
                value="tablet",
                previous_modifier=0.50,
                new_modifier=0.00,
                reason="zero_visits",
            ),
            Decision(
                tenant_id=tenant.id,
                run_id=run.id,
                targeting_module="geo",
                targeting_key="country",
                value="IT",
                previous_modifier=1.00,
                new_modifier=1.00,
                reason="on_target",
            ),
        ]
    )
    await db_session.flush()

    summary = await get_run_summary(
        db_session, run_id=run.id, tenant_id=tenant.id,
    )
    assert summary is not None
    assert summary.run_id == run.id
    assert summary.line_item_id == line_item.id
    assert summary.status == "succeeded"

    # KPIs
    assert summary.kpis.spend == pytest.approx(600.00)
    assert summary.kpis.impressions == 200_000
    assert summary.kpis.clicks == 2_000
    assert summary.kpis.conversions == 400
    assert summary.kpis.ctr == pytest.approx(2_000 / 200_000)
    assert summary.kpis.cpm == pytest.approx(1000 * 600.00 / 200_000)
    assert summary.kpis.cpa == pytest.approx(600.00 / 400)
    assert summary.kpis.roas == pytest.approx(1.5)
    assert summary.kpis.cpv_target == pytest.approx(0.50)
    assert summary.kpis.cpv_observed == pytest.approx(0.42)

    # Distribution falls back to live aggregation (denorm cols are NULL).
    dist = summary.distribution
    assert dist.n_terms_evaluated == 4
    assert dist.n_terms_changed == 3
    assert dist.n_terms_boosted == 1
    assert dist.n_terms_cut == 2  # 1.0->0.8 AND 0.5->0.0 both count as cut
    assert dist.n_terms_zeroed == 1


@pytest.mark.asyncio
async def test_get_run_summary_uses_denormalized_counters(db_session) -> None:
    """When the scheduler has filled n_terms_* on Run, we trust them."""
    from deevai_api.services.reporting import get_run_summary

    tenant, _, run = await _make_world(db_session, tenant_slug="rep-summary-denorm")
    run.n_terms_evaluated = 99
    run.n_terms_changed = 77
    run.n_terms_boosted = 33
    run.n_terms_cut = 44
    run.n_terms_zeroed = 5
    await db_session.flush()

    summary = await get_run_summary(
        db_session, run_id=run.id, tenant_id=tenant.id,
    )
    assert summary is not None
    assert summary.distribution.n_terms_evaluated == 99
    assert summary.distribution.n_terms_changed == 77
    assert summary.distribution.n_terms_boosted == 33
    assert summary.distribution.n_terms_cut == 44
    assert summary.distribution.n_terms_zeroed == 5


@pytest.mark.asyncio
async def test_get_run_summary_handles_zero_impressions(db_session) -> None:
    from deevai_api.services.reporting import get_run_summary

    tenant, _, run = await _make_world(db_session, tenant_slug="rep-summary-zero")
    run.blended_impressions = 0
    run.blended_clicks = 0
    run.blended_visits = 0
    run.blended_spend = 0.0
    await db_session.flush()

    summary = await get_run_summary(
        db_session, run_id=run.id, tenant_id=tenant.id,
    )
    assert summary is not None
    # No division-by-zero — all derived rates must be None.
    assert summary.kpis.ctr is None
    assert summary.kpis.cpm is None
    assert summary.kpis.cpa is None


@pytest.mark.asyncio
async def test_top_movers_ordering_and_limit(db_session) -> None:
    from deevai_api.services.reporting import get_top_movers

    tenant, _, run = await _make_world(db_session, tenant_slug="rep-movers")

    # Build 6 decisions with distinct |delta|.
    deltas = [
        ("a", 1.00, 1.05),   # delta 0.05
        ("b", 1.00, 0.30),   # delta -0.70 (biggest)
        ("c", 0.50, 0.80),   # delta 0.30
        ("d", 1.00, 1.00),   # delta 0 (smallest)
        ("e", 1.20, 0.60),   # delta -0.60
        ("f", 0.80, 1.30),   # delta 0.50
    ]
    for value, old, new in deltas:
        db_session.add(
            Decision(
                tenant_id=tenant.id,
                run_id=run.id,
                targeting_module="device",
                targeting_key="type",
                value=value,
                previous_modifier=old,
                new_modifier=new,
                reason="under_target",
            )
        )
    await db_session.flush()

    movers = await get_top_movers(
        db_session, run_id=run.id, tenant_id=tenant.id, limit=3,
    )
    assert [m.value for m in movers] == ["b", "e", "f"]
    # abs_delta is monotonically non-increasing
    abs_deltas = [m.abs_delta for m in movers]
    assert abs_deltas == sorted(abs_deltas, reverse=True)
    # delta signs preserved
    assert movers[0].delta < 0
    assert movers[2].delta > 0


@pytest.mark.asyncio
async def test_top_movers_cross_tenant_returns_empty(db_session) -> None:
    from deevai_api.services.reporting import get_top_movers

    _, _, run = await _make_world(db_session, tenant_slug="rep-movers-iso")
    db_session.add(
        Decision(
            tenant_id=run.tenant_id,
            run_id=run.id,
            targeting_module="device",
            targeting_key="type",
            value="x",
            previous_modifier=1.0,
            new_modifier=2.0,
            reason="under_target",
        )
    )
    await db_session.flush()

    other = Tenant(
        name="Intruder", slug="rep-movers-iso-other", plan="beta", status="active",
    )
    db_session.add(other)
    await db_session.flush()

    assert (
        await get_top_movers(
            db_session, run_id=run.id, tenant_id=other.id, limit=10,
        )
        == []
    )


@pytest.mark.asyncio
async def test_constraint_events_only_for_this_run(db_session) -> None:
    from deevai_api.services.reporting import get_constraint_events

    tenant, line_item, run_a = await _make_world(
        db_session, tenant_slug="rep-constraints", week_label="2026-W19",
    )

    # A second run on the same line item.
    now = datetime.now(timezone.utc)
    run_b = Run(
        tenant_id=tenant.id,
        line_item_id=line_item.id,
        week_label="2026-W20",
        window_start=now - timedelta(days=7),
        window_end=now,
        status="succeeded",
        started_at=now,
    )
    db_session.add(run_b)
    await db_session.flush()

    # Run A: 2 constraint hits + 1 unrelated decision
    db_session.add_all(
        [
            Decision(
                tenant_id=tenant.id,
                run_id=run_a.id,
                targeting_module="device",
                targeting_key="type",
                value="mobile",
                previous_modifier=1.00,
                new_modifier=1.00,
                reason="constraint_violated",
                note=(
                    "constraint_violated_cpc: observed 0.2500 lte 0.1500 (freeze)"
                ),
            ),
            Decision(
                tenant_id=tenant.id,
                run_id=run_a.id,
                targeting_module="device",
                targeting_key="type",
                value="desktop",
                previous_modifier=1.00,
                new_modifier=0.00,
                reason="constraint_violated",
                note=(
                    "constraint_violated_fraud_rate: observed 0.0500 gte 0.0150 (kill)"
                ),
            ),
            Decision(
                tenant_id=tenant.id,
                run_id=run_a.id,
                targeting_module="geo",
                targeting_key="country",
                value="IT",
                previous_modifier=1.00,
                new_modifier=1.10,
                reason="under_target",
            ),
            # Run B's constraint event should NOT leak into Run A.
            Decision(
                tenant_id=tenant.id,
                run_id=run_b.id,
                targeting_module="device",
                targeting_key="type",
                value="tablet",
                previous_modifier=1.00,
                new_modifier=1.00,
                reason="constraint_violated",
                note=(
                    "constraint_violated_viewability: observed 0.2000 lte 0.5000 (throttle)"
                ),
            ),
        ]
    )
    await db_session.flush()

    events = await get_constraint_events(
        db_session, run_id=run_a.id, tenant_id=tenant.id,
    )
    assert len(events) == 2
    by_metric = {e.metric: e for e in events}
    assert set(by_metric) == {"cpc", "fraud_rate"}

    cpc = by_metric["cpc"]
    assert cpc.observed == pytest.approx(0.25)
    assert cpc.operator == "lte"
    assert cpc.threshold == pytest.approx(0.15)
    assert cpc.policy == "freeze"

    fraud = by_metric["fraud_rate"]
    assert fraud.policy == "kill"
    assert fraud.new_modifier == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_constraint_events_tolerate_malformed_note(db_session) -> None:
    from deevai_api.services.reporting import get_constraint_events

    tenant, _, run = await _make_world(
        db_session, tenant_slug="rep-constraints-malformed",
    )
    db_session.add(
        Decision(
            tenant_id=tenant.id,
            run_id=run.id,
            targeting_module="device",
            targeting_key="type",
            value="mobile",
            previous_modifier=1.0,
            new_modifier=1.0,
            reason="constraint_violated",
            note="legacy free-text note",
        )
    )
    await db_session.flush()

    events = await get_constraint_events(
        db_session, run_id=run.id, tenant_id=tenant.id,
    )
    assert len(events) == 1
    # Parsing failed gracefully — structured fields are None, raw kept.
    assert events[0].metric is None
    assert events[0].policy is None
    assert events[0].raw_note == "legacy free-text note"


@pytest.mark.asyncio
async def test_line_item_run_summaries_pagination(db_session) -> None:
    from deevai_api.services.reporting import get_line_item_run_summaries

    tenant, line_item, first_run = await _make_world(
        db_session, tenant_slug="rep-li-pagination", week_label="2026-W14",
    )

    # Create 4 more runs with strictly increasing started_at.
    base = first_run.started_at
    for i in range(4):
        db_session.add(
            Run(
                tenant_id=tenant.id,
                line_item_id=line_item.id,
                week_label=f"2026-W{15 + i}",
                window_start=base + timedelta(days=7 * i),
                window_end=base + timedelta(days=7 * i + 7),
                status="succeeded",
                started_at=base + timedelta(days=7 * (i + 1)),
            )
        )
    await db_session.flush()

    # limit=3 should give us the 3 most recent runs, newest first.
    summaries = await get_line_item_run_summaries(
        db_session, line_item_id=line_item.id, tenant_id=tenant.id, limit=3,
    )
    assert len(summaries) == 3
    started = [s.started_at for s in summaries]
    assert started == sorted(started, reverse=True)

    # limit larger than total runs returns all 5.
    all_summaries = await get_line_item_run_summaries(
        db_session, line_item_id=line_item.id, tenant_id=tenant.id, limit=50,
    )
    assert len(all_summaries) == 5

    # Unknown line item → empty list (router handles 404 separately).
    assert (
        await get_line_item_run_summaries(
            db_session,
            line_item_id="00000000-0000-0000-0000-000000000099",
            tenant_id=tenant.id,
            limit=10,
        )
        == []
    )


# =============================================================== HTTP tests


@pytest.mark.asyncio
async def test_http_run_summary_happy_path(db_session) -> None:
    tenant, line_item, run = await _make_world(db_session, tenant_slug="rep-http-ok")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        resp = await client.get(f"/v1/reports/runs/{run.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["runId"] == run.id
        assert body["lineItemId"] == line_item.id
        assert body["kpis"]["spend"] == pytest.approx(600.00)
        assert "distribution" in body
        break

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_http_run_summary_cross_tenant_returns_404(db_session) -> None:
    """A run owned by tenant A is invisible to tenant B's JWT."""
    _, _, run = await _make_world(db_session, tenant_slug="rep-http-iso-a")

    intruder = Tenant(
        name="B", slug="rep-http-iso-b", plan="beta", status="active",
    )
    db_session.add(intruder)
    await db_session.flush()

    _override_claims(intruder.id)

    async for client in _client(db_session):
        resp = await client.get(f"/v1/reports/runs/{run.id}")
        # We return 404 (not 403) on purpose: don't even confirm the run
        # exists for someone else's tenant.
        assert resp.status_code == 404
        break

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_http_run_summary_requires_bearer(db_session) -> None:
    """No Authorization header → 401 (claims dep is strict)."""
    _, _, run = await _make_world(db_session, tenant_slug="rep-http-noauth")
    # Do NOT override get_current_user_claims — let the real dep reject.
    async def override_session() -> AI:
        yield db_session

    app.dependency_overrides[get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/v1/reports/runs/{run.id}")
        assert resp.status_code == 401

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_http_movers_limit_and_order(db_session) -> None:
    tenant, _, run = await _make_world(db_session, tenant_slug="rep-http-movers")

    for value, old, new in [
        ("big-cut", 1.00, 0.20),
        ("small-bump", 1.00, 1.05),
        ("medium-bump", 1.00, 1.40),
    ]:
        db_session.add(
            Decision(
                tenant_id=tenant.id,
                run_id=run.id,
                targeting_module="device",
                targeting_key="type",
                value=value,
                previous_modifier=old,
                new_modifier=new,
                reason="under_target",
            )
        )
    await db_session.flush()

    _override_claims(tenant.id)

    async for client in _client(db_session):
        resp = await client.get(f"/v1/reports/runs/{run.id}/movers?limit=2")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["value"] == "big-cut"
        assert body[1]["value"] == "medium-bump"
        # delta exposed and signed correctly
        assert body[0]["delta"] < 0
        assert body[1]["delta"] > 0
        break

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_http_constraints_returns_only_violation_rows(db_session) -> None:
    tenant, _, run = await _make_world(db_session, tenant_slug="rep-http-constraints")
    db_session.add_all(
        [
            Decision(
                tenant_id=tenant.id,
                run_id=run.id,
                targeting_module="device",
                targeting_key="type",
                value="mobile",
                previous_modifier=1.00,
                new_modifier=1.00,
                reason="constraint_violated",
                note="constraint_violated_cpc: observed 0.30 lte 0.15 (freeze)",
            ),
            Decision(
                tenant_id=tenant.id,
                run_id=run.id,
                targeting_module="geo",
                targeting_key="country",
                value="IT",
                previous_modifier=1.00,
                new_modifier=1.10,
                reason="under_target",
            ),
        ]
    )
    await db_session.flush()

    _override_claims(tenant.id)

    async for client in _client(db_session):
        resp = await client.get(f"/v1/reports/runs/{run.id}/constraints")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["metric"] == "cpc"
        assert body[0]["policy"] == "freeze"
        break

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_http_line_item_runs_pagination(db_session) -> None:
    tenant, line_item, first_run = await _make_world(
        db_session, tenant_slug="rep-http-li", week_label="2026-W10",
    )
    base = first_run.started_at
    for i in range(2):
        db_session.add(
            Run(
                tenant_id=tenant.id,
                line_item_id=line_item.id,
                week_label=f"2026-W{11 + i}",
                window_start=base + timedelta(days=7 * i),
                window_end=base + timedelta(days=7 * i + 7),
                status="succeeded",
                started_at=base + timedelta(days=7 * (i + 1)),
            )
        )
    await db_session.flush()

    _override_claims(tenant.id)

    async for client in _client(db_session):
        resp = await client.get(
            f"/v1/reports/line-items/{line_item.id}/runs?limit=2"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        # newest first
        assert body[0]["weekLabel"] != "2026-W10"

        # Bad limit → 422 (FastAPI Query validation)
        bad = await client.get(
            f"/v1/reports/line-items/{line_item.id}/runs?limit=0"
        )
        assert bad.status_code == 422

        # Unknown line item → 404
        notfound = await client.get(
            "/v1/reports/line-items/00000000-0000-0000-0000-000000000099/runs"
        )
        assert notfound.status_code == 404
        break

    app.dependency_overrides.clear()
