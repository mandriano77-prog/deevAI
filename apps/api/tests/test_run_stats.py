"""Tests for the denormalized run-counter pipeline.

Three layers:

1. :func:`deevai_api.services.run_stats.compute_run_counters` — pure
   function, mixed happy paths (boost/cut/zero/no-change).
2. Scheduler integration — after :func:`run_for_line_item` commits a
   ``Run``, the ``n_terms_*`` columns are non-NULL and match the
   live aggregation from the same decisions.
3. The standalone backfill script — starting from a Run with NULL
   counters and a handful of decisions, running ``backfill`` flips
   the counters to the same values the live fallback would produce.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from deevai_api.models import (
    Advertiser,
    Decision,
    Integration,
    LineItem,
    Run,
    Setting,
    Tenant,
)
from deevai_api.services.run_stats import compute_run_counters


# --------------------------------------------------------------- pure tests


def _mod(prev: float, new: float) -> SimpleNamespace:
    return SimpleNamespace(previous_modifier=prev, new_modifier=new)


def test_compute_run_counters_empty() -> None:
    counters = compute_run_counters([])
    assert counters == {
        "n_terms_evaluated": 0,
        "n_terms_changed": 0,
        "n_terms_boosted": 0,
        "n_terms_cut": 0,
        "n_terms_zeroed": 0,
    }


def test_compute_run_counters_mixed_happy_path() -> None:
    decisions = [
        _mod(1.0, 1.2),   # boost
        _mod(1.0, 0.8),   # cut
        _mod(0.5, 0.0),   # cut + zero
        _mod(0.0, 0.0),   # zeroed (no-change but already at zero)
        _mod(1.0, 1.0),   # no-change
    ]
    counters = compute_run_counters(decisions)
    assert counters == {
        "n_terms_evaluated": 5,
        "n_terms_changed": 3,    # 1 boost + 2 cuts
        "n_terms_boosted": 1,
        "n_terms_cut": 2,        # 1.0→0.8 and 0.5→0.0
        "n_terms_zeroed": 2,     # 0.5→0.0 and 0.0→0.0
    }


def test_compute_run_counters_accepts_decimals() -> None:
    """Numeric columns hand us Decimals — they must coerce cleanly."""
    from decimal import Decimal

    decisions = [
        _mod(Decimal("1.00"), Decimal("1.50")),
        _mod(Decimal("0.80"), Decimal("0.00")),
    ]
    counters = compute_run_counters(decisions)
    assert counters["n_terms_evaluated"] == 2
    assert counters["n_terms_boosted"] == 1
    assert counters["n_terms_cut"] == 1
    assert counters["n_terms_zeroed"] == 1


# ====================================================== scheduler integration


async def _seed_line_item(db_session, slug: str = "runstats") -> tuple[Tenant, LineItem]:
    tenant = Tenant(name=f"T-{slug}", slug=f"test-{slug}", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()

    db_session.add(Setting(tenant_id=tenant.id, default_cpv_target=0.5))
    integration = Integration(
        tenant_id=tenant.id, name="Amazon", provider="amazon_dsp",
    )
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
        amazon_line_item_id="run-stats-1",
        cpv_target=0.5,
    )
    db_session.add(li)
    await db_session.flush()
    return tenant, li


@pytest.mark.asyncio
async def test_scheduler_populates_run_counters(db_session) -> None:
    """``run_for_line_item`` must populate ``n_terms_*`` at commit time."""
    from deevai_api.services.scheduler import run_for_line_item

    tenant, li = await _seed_line_item(db_session, slug="sched-populate")

    run = await run_for_line_item(
        db_session,
        tenant_id=tenant.id,
        line_item_id=li.id,
    )

    # Counters must be non-NULL on the row itself.
    assert run.n_terms_evaluated is not None
    assert run.n_terms_changed is not None
    assert run.n_terms_boosted is not None
    assert run.n_terms_cut is not None
    assert run.n_terms_zeroed is not None

    # And they must agree with the live aggregation across the
    # committed Decision rows.
    decisions = (
        await db_session.execute(
            select(Decision).where(Decision.run_id == run.id),
        )
    ).scalars().all()
    expected = compute_run_counters(decisions)
    assert run.n_terms_evaluated == expected["n_terms_evaluated"]
    assert run.n_terms_changed == expected["n_terms_changed"]
    assert run.n_terms_boosted == expected["n_terms_boosted"]
    assert run.n_terms_cut == expected["n_terms_cut"]
    assert run.n_terms_zeroed == expected["n_terms_zeroed"]
    # Sanity: the scheduler is fed non-trivial mock data.
    assert run.n_terms_evaluated > 0


@pytest.mark.asyncio
async def test_reporting_returns_same_distribution_as_counters(db_session) -> None:
    """The denormalized counters and the live fallback must agree."""
    from deevai_api.services.reporting import get_run_summary
    from deevai_api.services.scheduler import run_for_line_item

    tenant, li = await _seed_line_item(db_session, slug="sched-report")
    run = await run_for_line_item(
        db_session, tenant_id=tenant.id, line_item_id=li.id,
    )

    # Path A: read using the populated counters.
    populated = await get_run_summary(
        db_session, run_id=run.id, tenant_id=tenant.id,
    )
    assert populated is not None
    populated_dist = populated.distribution

    # Path B: blank the counters and read again -- reporting must
    # fall back to live aggregation. We mutate the attached row
    # directly: SQLAlchemy's identity map hands the same instance
    # back to ``get_run`` inside the service, so the NULL counters
    # are visible without an expire/refresh round-trip (which would
    # need greenlet here).
    run.n_terms_evaluated = None
    run.n_terms_changed = None
    run.n_terms_boosted = None
    run.n_terms_cut = None
    run.n_terms_zeroed = None
    await db_session.flush()

    fallback = await get_run_summary(
        db_session, run_id=run.id, tenant_id=tenant.id,
    )
    assert fallback is not None
    fallback_dist = fallback.distribution

    assert populated_dist == fallback_dist


# =============================================================== backfill


def _load_backfill_module():
    """Import the standalone script as a regular module."""
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "backfill_run_counters.py"
    )
    spec = importlib.util.spec_from_file_location(
        "backfill_run_counters", path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _seed_run_with_null_counters(
    db_session,
    *,
    slug: str,
    pairs: list[tuple[float, float]],
) -> tuple[Tenant, Run]:
    tenant, li = await _seed_line_item(db_session, slug=slug)
    now = datetime.now(timezone.utc)
    run = Run(
        tenant_id=tenant.id,
        line_item_id=li.id,
        week_label="2026-W20",
        window_start=now - timedelta(days=7),
        window_end=now,
        status="succeeded",
        started_at=now - timedelta(minutes=1),
        completed_at=now,
        blended_cpv_target=0.5,
        blended_cpv_observed=0.42,
        n_decisions=len(pairs),
        n_changes_proposed=sum(1 for p, n in pairs if p != n),
        n_changes_applied=0,
        # n_terms_* deliberately left NULL.
    )
    db_session.add(run)
    await db_session.flush()

    for i, (prev, new) in enumerate(pairs):
        db_session.add(
            Decision(
                tenant_id=tenant.id,
                run_id=run.id,
                targeting_module="device",
                targeting_key="type",
                value=f"slot-{i}",
                previous_modifier=prev,
                new_modifier=new,
                reason="under_target",
            )
        )
    await db_session.flush()
    return tenant, run


@pytest.mark.asyncio
async def test_backfill_populates_null_counters(db_session) -> None:
    backfill_mod = _load_backfill_module()

    tenant, run = await _seed_run_with_null_counters(
        db_session,
        slug="backfill-null",
        # Mix: 1 boost, 1 cut, 1 cut-to-zero, 1 no-change.
        pairs=[(1.0, 1.2), (1.0, 0.8), (0.5, 0.0), (1.0, 1.0)],
    )

    # Sanity: row starts with NULL counters.
    assert run.n_terms_evaluated is None

    updated = await backfill_mod.backfill(db_session, batch_size=10)

    # backfill mutates the attached Run row directly; assert via
    # identity-map access (same instance, no lazy reload).
    assert updated == 1
    assert run.n_terms_evaluated == 4
    assert run.n_terms_changed == 3   # boost + 2 cuts
    assert run.n_terms_boosted == 1
    assert run.n_terms_cut == 2
    assert run.n_terms_zeroed == 1


@pytest.mark.asyncio
async def test_backfill_is_idempotent(db_session) -> None:
    """Re-running the backfill must be a no-op on already-populated runs."""
    backfill_mod = _load_backfill_module()

    tenant, run = await _seed_run_with_null_counters(
        db_session,
        slug="backfill-idempotent",
        pairs=[(1.0, 1.5), (0.8, 0.0)],
    )

    first = await backfill_mod.backfill(db_session, batch_size=10)
    assert first == 1

    # Second pass must not touch anything.
    second = await backfill_mod.backfill(db_session, batch_size=10)
    assert second == 0
