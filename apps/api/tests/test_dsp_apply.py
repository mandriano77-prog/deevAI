"""Tests for the dsp_apply orchestrator — DV360 wiring.

Covers:
- decisions_to_plan: DB rows → bidagent.Plan shape.
- _advertiser_id_from_integration: provider_config preferred, fallback OK.
- apply_run_to_dsp: dry-run path marks decisions applied, no HTTP.
- apply_run_to_dsp: live path (DSP_DRY_RUN=false) uses Dv360LineItemClient.
- apply_run_to_dsp: skips unsupported targeting types gracefully.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from bidagent.models import Plan
from bidagent.providers.dv360.bid_client import Dv360ApiResult

from deevai_api.config import get_settings
from deevai_api.models import (
    Advertiser,
    Decision,
    Integration,
    LineItem,
    Run,
    Tenant,
)
from deevai_api.services import dsp_apply
from deevai_api.services.dsp_apply import (
    DspApplyError,
    _advertiser_id_from_integration,
    apply_run_to_dsp,
    decisions_to_plan,
)


# ---------------------------------------------------------------- factory helpers


async def _build_fixture_graph(db_session, *, with_approved: int = 2):
    """Create Tenant → Integration → Advertiser → LineItem → Run + Decisions."""
    tenant = Tenant(name="Acme", slug="acme", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()

    integration = Integration(
        tenant_id=tenant.id,
        provider="dv360",
        name="DV360 main",
        client_id="cid-123",
        provider_config={"advertiser_id": "999111", "partner_id": "p1"},
    )
    # bypass vault during tests by storing ciphertext-shaped bytes; the
    # property decrypts on read but we override via attribute assignment
    integration.client_secret = "secret-xyz"  # uses vault.encrypt under the hood
    integration.refresh_token = "refresh-xyz"
    db_session.add(integration)
    await db_session.flush()

    advertiser = Advertiser(
        tenant_id=tenant.id,
        integration_id=integration.id,
        amazon_advertiser_id="ADV-FALLBACK-1",
        name="Acme EU",
        currency="EUR",
        country="IT",
        status="active",
    )
    db_session.add(advertiser)
    await db_session.flush()

    line_item = LineItem(
        tenant_id=tenant.id,
        advertiser_id=advertiser.id,
        amazon_line_item_id="123456789",  # DV360 numeric ID
        name="LI demo",
        cpv_target=Decimal("0.50"),
        mode="active",
        status="active",
    )
    db_session.add(line_item)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    run = Run(
        tenant_id=tenant.id,
        line_item_id=line_item.id,
        week_label="2026-W20",
        window_start=now - timedelta(days=7),
        window_end=now,
        status="succeeded",
        blended_cpv_observed=Decimal("0.55"),
        blended_visits=1000,
        blended_spend=Decimal("550.00"),
    )
    db_session.add(run)
    await db_session.flush()

    # Two approved decisions on supported DV360 targeting types.
    decisions = []
    for i in range(with_approved):
        d = Decision(
            tenant_id=tenant.id,
            run_id=run.id,
            targeting_module="device",
            targeting_key="device_type",
            value="MOBILE" if i == 0 else "DESKTOP",
            previous_modifier=Decimal("1.0"),
            new_modifier=Decimal("1.2") if i == 0 else Decimal("0.8"),
            reason="under_target",
            status="approved",
        )
        db_session.add(d)
        decisions.append(d)

    # One proposed (not approved) — must be ignored.
    db_session.add(
        Decision(
            tenant_id=tenant.id,
            run_id=run.id,
            targeting_module="device",
            targeting_key="device_type",
            value="TABLET",
            previous_modifier=Decimal("1.0"),
            new_modifier=Decimal("0.5"),
            reason="under_target",
            status="proposed",
        )
    )
    await db_session.flush()

    return tenant, integration, advertiser, line_item, run, decisions


# ----------------------------------------------------------------- pure helpers


def test_advertiser_id_prefers_provider_config():
    integ = Integration(
        tenant_id="t1",
        name="x",
        provider="dv360",
        provider_config={"advertiser_id": "FROM-CFG"},
    )
    adv = Advertiser(
        tenant_id="t1",
        integration_id="i1",
        amazon_advertiser_id="FROM-ADV",
        name="x",
    )
    assert _advertiser_id_from_integration(integ, adv) == "FROM-CFG"


def test_advertiser_id_falls_back_to_advertiser_row():
    integ = Integration(
        tenant_id="t1", name="x", provider="dv360", provider_config={},
    )
    adv = Advertiser(
        tenant_id="t1",
        integration_id="i1",
        amazon_advertiser_id="FROM-ADV",
        name="x",
    )
    assert _advertiser_id_from_integration(integ, adv) == "FROM-ADV"


# ----------------------------------------------------------------- DB-touching


@pytest.mark.asyncio
async def test_decisions_to_plan_builds_bidagent_shape(db_session):
    _, _, _, line_item, run, decisions = await _build_fixture_graph(db_session)
    plan = decisions_to_plan(line_item, run, decisions)

    assert isinstance(plan, Plan)
    assert plan.line_item_id == 123456789
    assert plan.line_item_name == "LI demo"
    assert plan.week_label == "2026-W20"
    assert len(plan.decisions) == 2
    assert plan.decisions[0].term.targeting_module == "device"
    assert plan.decisions[0].new_modifier == pytest.approx(1.2)


@pytest.mark.asyncio
async def test_apply_dry_run_marks_decisions_applied(db_session, monkeypatch):
    """In dry-run we never call HTTP and we mark every approved decision
    as ``applied`` with note ``[dry-run]``."""
    monkeypatch.setattr(get_settings(), "dsp_dry_run", True, raising=False)

    _, _, _, _, run, approved = await _build_fixture_graph(db_session)
    result = await apply_run_to_dsp(run=run, db=db_session)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["applied"] == 2
    for d in approved:
        await db_session.refresh(d)
        assert d.status == "applied"
        assert d.application_error == "[dry-run]"
        assert d.applied_at is not None


@pytest.mark.asyncio
async def test_apply_live_uses_bulk_edit_client(db_session, monkeypatch):
    """Live path: dsp_apply must build the DV360 payload and forward it to
    ``Dv360LineItemClient.bulk_edit_targeting``. We monkeypatch the client
    so the test never touches Google."""
    monkeypatch.setattr(get_settings(), "dsp_dry_run", False, raising=False)

    # Stub out Dv360Auth so no real token exchange happens.
    class _FakeAuth:
        def __init__(self, *a, **kw):
            pass

    monkeypatch.setattr(dsp_apply, "Dv360Auth", _FakeAuth)

    captured: dict = {}

    class _FakeClient:
        def __init__(self, *, auth, dry_run, **kw):
            captured["dry_run_arg"] = dry_run

        def bulk_edit_targeting(self, advertiser_id, body):
            captured["advertiser_id"] = advertiser_id
            captured["body"] = body
            return Dv360ApiResult(ok=True, status_code=200, body={"done": True})

    monkeypatch.setattr(dsp_apply, "Dv360LineItemClient", _FakeClient)

    _, _, _, _, run, approved = await _build_fixture_graph(db_session)
    result = await apply_run_to_dsp(run=run, db=db_session)

    assert result["ok"] is True
    assert result["dry_run"] is False
    assert result["applied"] == 2
    assert captured["dry_run_arg"] is False
    assert captured["advertiser_id"] == "999111"  # from provider_config
    assert captured["body"]["lineItemIds"] == ["123456789"]
    assert len(captured["body"]["createRequests"]) == 2

    for d in approved:
        await db_session.refresh(d)
        assert d.status == "applied"
        assert d.application_error is None


@pytest.mark.asyncio
async def test_apply_live_failure_marks_decisions_failed(
    db_session, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "dsp_dry_run", False, raising=False)

    class _FakeAuth:
        def __init__(self, *a, **kw):
            pass

    class _FakeClient:
        def __init__(self, *, auth, dry_run, **kw):
            pass

        def bulk_edit_targeting(self, advertiser_id, body):
            return Dv360ApiResult(
                ok=False, status_code=403, body={"error": "denied"},
                note="http 403",
            )

    monkeypatch.setattr(dsp_apply, "Dv360Auth", _FakeAuth)
    monkeypatch.setattr(dsp_apply, "Dv360LineItemClient", _FakeClient)

    _, _, _, _, run, approved = await _build_fixture_graph(db_session)
    result = await apply_run_to_dsp(run=run, db=db_session)

    assert result["ok"] is False
    assert result["applied"] == 0
    assert result["status_code"] == 403

    for d in approved:
        await db_session.refresh(d)
        assert d.status == "failed_to_apply"
        assert "http 403" in (d.application_error or "")


@pytest.mark.asyncio
async def test_apply_no_approved_decisions_short_circuits(
    db_session, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "dsp_dry_run", True, raising=False)
    _, _, _, _, run, _ = await _build_fixture_graph(db_session, with_approved=0)
    result = await apply_run_to_dsp(run=run, db=db_session)
    assert result["ok"] is True
    assert result["applied"] == 0
    assert "no approved decisions" in result["note"]
