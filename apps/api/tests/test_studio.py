"""Studio — DB + service + REST surface for Custom Bidding scripts.

The tests intentionally mirror the structure of ``test_reporting.py``:
the ``api_client`` fixture from ``conftest.py`` only overrides
``get_current_tenant_id``, so for studio (which uses JWT claims) we
override ``get_current_user_claims`` per test.

Coverage targets (from the sprint brief):
  * create_script happy + 422 on weights-sum mismatch + 422 on negatives
  * create + simulate chain: lifecycle draft→simulated, distribution shape
  * list_scripts: filtering, pagination, tenant scoping
  * get_script: 404 cross-tenant, returns latest_simulation when present
  * archive_script: 204 + hidden from default list
  * no PATCH endpoint exists → script_source is immutable via API
  * determinism: same name + same weights → same sha256
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import AsyncIterator as AI

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from deevai_api.db import get_session
from deevai_api.deps import get_current_user_claims
from deevai_api.main import app
from deevai_api.models import (
    CustomBiddingScript,
    ObjectiveWeight,
    SimulationRun,
    Tenant,
)


# ───────────────────────────────────────────────────────────── fixtures


def _override_claims(tenant_id: str, user_id: str | None = "test-user") -> None:
    """Force the studio routes to see ``tenant_id`` via JWT claims."""

    async def fake_claims() -> dict:
        return {"sub": user_id, "tid": tenant_id, "role": "owner"}

    app.dependency_overrides[get_current_user_claims] = fake_claims


async def _client(db_session) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AI:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _make_tenant(db_session, slug: str) -> Tenant:
    tenant = Tenant(name=f"T-{slug}", slug=slug, plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    return tenant


# Canonical "balanced" payload — covers the all-three-objectives path.
_BALANCED = {
    "name": "Balanced",
    "weights": {"performance": 50, "quality": 30, "reach": 20},
}
# Reach-only payload — exercises the no-floodlight branch.
_REACH_ONLY = {
    "name": "ReachOnly",
    "weights": {"performance": 0, "quality": 0, "reach": 100},
}


# ───────────────────────────────────────────────────── create happy path


@pytest.mark.asyncio
async def test_create_script_happy_path_persists_dsl_and_weights(db_session):
    tenant = await _make_tenant(db_session, "studio-create-ok")
    _override_claims(tenant.id)

    script_id = None
    async for client in _client(db_session):
        resp = await client.post("/v1/studio/scripts", json=_BALANCED)
        assert resp.status_code == 201, resp.text
        body = resp.json()

        # Camel-case JSON contract (via ApiModel alias generator)
        assert body["name"] == "Balanced"
        assert body["status"] == "draft"
        assert body["tenantId"] == tenant.id
        assert len(body["scriptSha256"]) == 64
        assert body["sizeBytes"] > 0
        assert body["weights"] == {
            "performance": 50, "quality": 30, "reach": 20,
        }
        script_id = body["id"]
        break

    # The script + weights row exist with the right shape.
    rs = await db_session.execute(
        select(CustomBiddingScript).where(CustomBiddingScript.tenant_id == tenant.id)
    )
    scripts = list(rs.scalars().all())
    assert len(scripts) == 1
    assert scripts[0].size_bytes > 0
    assert "Custom Bidding" in scripts[0].script_source

    ow = await db_session.execute(
        select(ObjectiveWeight).where(ObjectiveWeight.script_id == scripts[0].id)
    )
    weight_row = ow.scalar_one()
    assert weight_row.performance_pct == 50
    assert weight_row.quality_pct == 30
    assert weight_row.reach_pct == 20

    app.dependency_overrides.clear()


# ──────────────────────────────────────────── create validation errors


@pytest.mark.asyncio
async def test_create_script_rejects_weights_not_summing_to_100(db_session):
    tenant = await _make_tenant(db_session, "studio-create-badsum")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        resp = await client.post(
            "/v1/studio/scripts",
            json={
                "name": "BadSum",
                "weights": {"performance": 50, "quality": 30, "reach": 10},
            },
        )
        # Pydantic v2 raises 422 on model_validator failures
        assert resp.status_code == 422
        # The error mentions the sum so the FE can pinpoint the field.
        assert "100" in resp.text
        break

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_script_rejects_negative_weights(db_session):
    tenant = await _make_tenant(db_session, "studio-create-neg")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        resp = await client.post(
            "/v1/studio/scripts",
            json={
                "name": "Negative",
                "weights": {"performance": 110, "quality": -20, "reach": 10},
            },
        )
        assert resp.status_code == 422
        break

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_script_rejects_duplicate_name_for_tenant(db_session):
    tenant = await _make_tenant(db_session, "studio-create-dup")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        r1 = await client.post("/v1/studio/scripts", json=_BALANCED)
        assert r1.status_code == 201

        r2 = await client.post("/v1/studio/scripts", json=_BALANCED)
        # Unique constraint on (tenant_id, name) → 409
        assert r2.status_code == 409
        break

    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────── simulate chain


@pytest.mark.asyncio
async def test_simulate_script_transitions_draft_to_simulated(db_session):
    tenant = await _make_tenant(db_session, "studio-sim-chain")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        # 1) Create — status should be draft
        r1 = await client.post("/v1/studio/scripts", json=_BALANCED)
        assert r1.status_code == 201
        script_id = r1.json()["id"]
        assert r1.json()["status"] == "draft"

        # 2) Simulate — default body (synthetic, 5000)
        r2 = await client.post(
            f"/v1/studio/scripts/{script_id}/simulate", json={},
        )
        assert r2.status_code == 200, r2.text
        report = r2.json()

        # Distribution shape is what the UI consumes (camelCase).
        assert "distribution" in report
        dist = report["distribution"]
        assert {"p10", "p25", "p50", "p75", "p90", "p99", "mean", "stddev"} <= (
            set(dist.keys())
        )
        # The 'pctAbove500' alias is the FE's pivot field
        assert "pctAbove500" in dist or "pct_above_500" in dist
        assert report["nImpressions"] == 5000
        assert report["nScored"] + report["nExcluded"] == report["nImpressions"]
        # Top winners/losers are capped at 5 in the API contract.
        assert len(report["topWinners"]) <= 5
        assert len(report["topLosers"]) <= 5

        # 3) Re-fetch — status flipped to simulated, simulation persisted.
        r3 = await client.get(f"/v1/studio/scripts/{script_id}")
        assert r3.status_code == 200
        detail = r3.json()
        assert detail["status"] == "simulated"
        assert detail["scriptSource"]
        assert detail["latestSimulation"] is not None
        assert detail["latestSimulation"]["nImpressions"] == 5000

        break

    # The SimulationRun row exists with the right tenant.
    runs = await db_session.execute(
        select(SimulationRun).where(SimulationRun.tenant_id == tenant.id)
    )
    runs_list = list(runs.scalars().all())
    assert len(runs_list) == 1
    assert runs_list[0].dataset_kind == "synthetic"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_simulate_unknown_script_returns_404(db_session):
    tenant = await _make_tenant(db_session, "studio-sim-404")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        resp = await client.post(
            "/v1/studio/scripts/00000000-0000-0000-0000-000000000000/simulate",
            json={},
        )
        assert resp.status_code == 404
        break

    app.dependency_overrides.clear()


# ──────────────────────────────────────────────── list_scripts surface


@pytest.mark.asyncio
async def test_list_scripts_excludes_archived_by_default(db_session):
    tenant = await _make_tenant(db_session, "studio-list-archive")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        r1 = await client.post("/v1/studio/scripts", json=_BALANCED)
        sid_1 = r1.json()["id"]

        r2 = await client.post("/v1/studio/scripts", json=_REACH_ONLY)
        sid_2 = r2.json()["id"]
        assert sid_1 != sid_2

        # Archive #1
        rd = await client.delete(f"/v1/studio/scripts/{sid_1}")
        assert rd.status_code == 204

        # Default list: only the non-archived one
        rl = await client.get("/v1/studio/scripts")
        assert rl.status_code == 200
        ids = [s["id"] for s in rl.json()]
        assert sid_1 not in ids
        assert sid_2 in ids

        # status=archived filter brings it back
        ra = await client.get("/v1/studio/scripts?status=archived")
        ids_arch = [s["id"] for s in ra.json()]
        assert ids_arch == [sid_1]

        break

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_scripts_pagination(db_session):
    tenant = await _make_tenant(db_session, "studio-list-page")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        for i in range(3):
            r = await client.post(
                "/v1/studio/scripts",
                json={
                    "name": f"Script{i}",
                    "weights": {"performance": 100, "quality": 0, "reach": 0},
                },
            )
            assert r.status_code == 201, r.text

        # limit=2 / offset=0|2
        r1 = await client.get("/v1/studio/scripts?limit=2&offset=0")
        assert len(r1.json()) == 2
        r2 = await client.get("/v1/studio/scripts?limit=2&offset=2")
        assert len(r2.json()) == 1
        break

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_scripts_is_tenant_scoped(db_session):
    """Scripts created by tenant A must not appear in tenant B's list."""
    tenant_a = await _make_tenant(db_session, "studio-iso-a")
    tenant_b = await _make_tenant(db_session, "studio-iso-b")

    # Create one script as tenant A
    _override_claims(tenant_a.id)
    async for client in _client(db_session):
        r = await client.post("/v1/studio/scripts", json=_BALANCED)
        assert r.status_code == 201
        break

    # List as tenant B — must be empty
    _override_claims(tenant_b.id)
    async for client in _client(db_session):
        rl = await client.get("/v1/studio/scripts")
        assert rl.status_code == 200
        assert rl.json() == []
        break

    app.dependency_overrides.clear()


# ──────────────────────────────────────────────────── get_script 404


@pytest.mark.asyncio
async def test_get_script_cross_tenant_returns_404(db_session):
    """Per reporting.py pattern: 404 (not 403) so we don't even
    confirm that another tenant's script exists."""
    tenant_a = await _make_tenant(db_session, "studio-get-a")
    tenant_b = await _make_tenant(db_session, "studio-get-b")

    sid = None
    _override_claims(tenant_a.id)
    async for client in _client(db_session):
        r = await client.post("/v1/studio/scripts", json=_BALANCED)
        sid = r.json()["id"]
        break

    _override_claims(tenant_b.id)
    async for client in _client(db_session):
        rg = await client.get(f"/v1/studio/scripts/{sid}")
        assert rg.status_code == 404
        # And the destructive endpoint also 404s — no info leak.
        rd = await client.delete(f"/v1/studio/scripts/{sid}")
        assert rd.status_code == 404
        break

    app.dependency_overrides.clear()


# ─────────────────────────────────────────────── archive (soft-delete)


@pytest.mark.asyncio
async def test_archive_script_returns_204_and_preserves_row(db_session):
    """DELETE is soft — the row stays, only status flips to archived."""
    tenant = await _make_tenant(db_session, "studio-archive")
    _override_claims(tenant.id)

    sid = None
    async for client in _client(db_session):
        r = await client.post("/v1/studio/scripts", json=_BALANCED)
        sid = r.json()["id"]
        rd = await client.delete(f"/v1/studio/scripts/{sid}")
        assert rd.status_code == 204
        break

    # Row still there with status=archived (audit trail).
    rs = await db_session.execute(
        select(CustomBiddingScript).where(CustomBiddingScript.id == sid)
    )
    row = rs.scalar_one()
    assert row.status == "archived"

    app.dependency_overrides.clear()


# ─────────────────────────────────── no PATCH (script_source immutable)


@pytest.mark.asyncio
async def test_no_patch_endpoint_exposed_for_scripts(db_session):
    """The API never lets the FE edit the DSL directly — only the slider
    weights flow through ``POST /v1/studio/scripts``. Verifies that
    PATCH/PUT against the resource returns 405."""
    tenant = await _make_tenant(db_session, "studio-no-patch")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        r = await client.post("/v1/studio/scripts", json=_BALANCED)
        sid = r.json()["id"]

        rp = await client.patch(
            f"/v1/studio/scripts/{sid}",
            json={"script_source": "return 0"},
        )
        assert rp.status_code == 405  # Method Not Allowed

        ru = await client.put(
            f"/v1/studio/scripts/{sid}",
            json={"name": "x"},
        )
        assert ru.status_code == 405
        break

    app.dependency_overrides.clear()


# ────────────────────────────────────────────── determinism guarantee


@pytest.mark.asyncio
async def test_create_script_weights_roundtrip_byte_exact(db_session):
    """Weights persisted exactly; sha256 differs only when inputs change.

    Within a single tenant the bytes of the generated script include a
    wall-clock timestamp in the header comment, so two back-to-back
    API calls produce different sha256s — but the *weights* round-trip
    bit-exact, and the engine-level determinism is verified by
    :func:`test_generator_determinism_at_engine_level` below.
    """
    tenant = await _make_tenant(db_session, "studio-determinism-roundtrip")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        r1 = await client.post("/v1/studio/scripts", json=_BALANCED)
        body = r1.json()
        assert body["weights"] == _BALANCED["weights"]
        assert len(body["scriptSha256"]) == 64
        break

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generator_determinism_at_engine_level():
    """Engine-level guarantee the service relies on.

    The script_generator is deterministic when ``now`` is pinned. We
    pin it explicitly and confirm two back-to-back calls produce
    bit-identical sources for the same weights — that's the foundation
    of the FE's "nothing changed → don't re-upload" optimisation.
    """
    from datetime import datetime, timezone

    from bidagent.engines.custom_bidding import (
        ObjectiveId,
        TenantConfig,
        generate_script,
    )

    pinned = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    cfg = TenantConfig(
        weights={
            ObjectiveId.PERFORMANCE: 0.5,
            ObjectiveId.QUALITY: 0.3,
            ObjectiveId.REACH: 0.2,
        },
        floodlight_activity_id=999_999,
    )
    g1 = generate_script(cfg, tenant_id="t1", now=pinned)
    g2 = generate_script(cfg, tenant_id="t1", now=pinned)
    assert g1.source == g2.source
    assert g1.digest_sha256 == g2.digest_sha256


# ─────────────────────────────────── auth & unknown-id sanity


@pytest.mark.asyncio
async def test_studio_routes_require_bearer_token(db_session):
    """No claims override → real dep should reject with 401."""

    async def override_session() -> AI:
        yield db_session

    app.dependency_overrides[get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/studio/scripts")
        assert resp.status_code == 401

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_unknown_script_returns_404(db_session):
    tenant = await _make_tenant(db_session, "studio-get-404")
    _override_claims(tenant.id)

    async for client in _client(db_session):
        r = await client.get(
            "/v1/studio/scripts/00000000-0000-0000-0000-000000000000",
        )
        assert r.status_code == 404
        break

    app.dependency_overrides.clear()
