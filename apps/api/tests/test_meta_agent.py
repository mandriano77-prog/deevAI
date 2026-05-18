"""Meta-agent diagnose patterns and governance."""

from __future__ import annotations

import pytest

from deevai_api.models import Tenant
from deevai_api.services.meta_agent.diagnose import quick_diagnose
from deevai_api.services.meta_agent.governance import is_auto_applicable, validate_proposed_changes


def test_pattern_a_healthy_tradeoff() -> None:
    ctx = {
        "settings": {"default_cpv_target": 0.5},
        "runs": [
            {"blended_cpv_observed": 0.65, "blended_roas": 2.1},
            {"blended_cpv_observed": 0.50, "blended_roas": 1.8},
        ],
        "recent_decisions": [],
        "actions": [],
        "constraints": [],
    }
    out = quick_diagnose(ctx, "Il CPA è troppo alto questa settimana")
    assert out is not None
    assert out["proposed_changes"] == []


def test_pattern_b_low_movement() -> None:
    ctx = {
        "settings": {"id": "s1", "default_cpv_target": 0.4, "max_step_per_run": 0.20},
        "runs": [
            {"blended_cpv_observed": 0.55, "n_changes_proposed": 1, "n_decisions": 40},
            {"blended_cpv_observed": 0.52, "n_changes_proposed": 0, "n_decisions": 40},
            {"blended_cpv_observed": 0.50, "n_changes_proposed": 1, "n_decisions": 40},
        ],
        "recent_decisions": [],
        "actions": [],
        "constraints": [],
    }
    out = quick_diagnose(ctx, "CPA alto e poche modifiche")
    assert out is not None
    assert out["proposed_changes"][0]["field"] == "max_step_per_run"


def test_pattern_c_oscillation() -> None:
    ctx = {
        "settings": {"id": "s1", "max_step_per_run": 0.30},
        "runs": [],
        "recent_decisions": [
            {"previous_modifier": 1.0, "new_modifier": 1.2},
            {"previous_modifier": 1.2, "new_modifier": 0.9},
            {"previous_modifier": 0.9, "new_modifier": 1.1},
            {"previous_modifier": 1.1, "new_modifier": 0.85},
        ],
        "actions": [],
        "constraints": [],
    }
    out = quick_diagnose(ctx, "I modifier oscillano troppo")
    assert out is not None
    assert out["proposed_changes"][0]["to"] < 0.30


def test_pattern_d_constraints() -> None:
    ctx = {
        "settings": {},
        "runs": [],
        "recent_decisions": [
            {"reason": "constraint_violated_cpc"} for _ in range(4)
        ] + [{"reason": "over_target"} for _ in range(6)],
        "actions": [],
        "constraints": [{"metric": "cpc"}],
    }
    out = quick_diagnose(ctx, "Troppi term bloccati")
    assert out is not None
    assert out["proposed_changes"] == []


def test_pattern_e_downstream() -> None:
    ctx = {
        "settings": {},
        "runs": [
            {"blended_visits": 50},
            {"blended_visits": 100},
        ],
        "recent_decisions": [],
        "actions": [
            {"name": "visita", "funnel_position": 1},
            {"name": "preliminare", "funnel_position": 2},
        ],
        "constraints": [],
    }
    out = quick_diagnose(ctx, "Drop nel funnel downstream")
    assert out is not None
    assert "downstream" in out["diagnosis"].lower()


def test_governance_blocks_action_tracking() -> None:
    changes = [{
        "entity": "actions",
        "entity_id": "a1",
        "field": "tracking_source",
        "from": "pixel",
        "to": "api",
        "reason": "test",
    }]
    assert validate_proposed_changes(changes)
    assert not is_auto_applicable(changes)


def test_governance_settings_auto() -> None:
    changes = [{
        "entity": "settings",
        "entity_id": "s1",
        "field": "max_step_per_run",
        "from": 0.2,
        "to": 0.25,
        "reason": "test",
    }]
    assert is_auto_applicable(changes)


@pytest.mark.asyncio
async def test_post_mortem_writes_verdict(db_session) -> None:
    from datetime import timedelta

    from deevai_api.models import AgentProposal
    from deevai_api.services.meta_agent.post_mortem import run_due_post_mortems
    from deevai_api.models import utcnow

    tenant = Tenant(name="PM", slug="test-pm", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    proposal = AgentProposal(
        agent_type="tuning",
        tenant_id=tenant.id,
        brief="test",
        proposed_changes=[],
        status="applied",
        applied_at=utcnow() - timedelta(days=8),
        post_mortem_due_at=utcnow() - timedelta(days=1),
        expected_impact={"primary_objective_delta_pct": 5.0},
    )
    db_session.add(proposal)
    await db_session.flush()

    count = await run_due_post_mortems(db_session)
    assert count == 1
    await db_session.refresh(proposal)
    assert proposal.post_mortem is not None
    assert proposal.post_mortem["verdict"] in ("match", "partial", "miss")


@pytest.mark.asyncio
async def test_apply_settings_writes_meta_agent_audit(db_session) -> None:
    from sqlalchemy import select

    from deevai_api.models import AuditLog, Setting
    from deevai_api.services.meta_agent.apply import apply_proposed_changes

    tenant = Tenant(name="Apply", slug="test-apply", plan="beta", status="active")
    db_session.add(tenant)
    await db_session.flush()
    setting = Setting(tenant_id=tenant.id, default_cpv_target=0.5, max_step_per_run=0.20)
    db_session.add(setting)
    await db_session.flush()

    await apply_proposed_changes(
        db_session,
        tenant_id=tenant.id,
        changes=[{
            "entity": "settings",
            "entity_id": setting.id,
            "field": "max_step_per_run",
            "from": 0.20,
            "to": 0.25,
            "reason": "test",
        }],
        actor_type="tuning_agent",
    )

    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.id,
                AuditLog.actor_type == "tuning_agent",
            ),
        )
    ).scalars().all()
    assert len(rows) >= 1
