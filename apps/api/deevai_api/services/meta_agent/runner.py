"""Orchestrate meta-agent brief → proposal → optional auto-apply."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import (
    Decision,
    HardConstraint,
    LineItem,
    AgentProposal,
    Run,
    Setting,
    utcnow,
)
from ...services.actions import get_action_funnel
from ...services.audit import snapshot_row
from ...services.optimization import get_strategy_for_scope, list_constraints
from . import apply_proposed_changes, is_auto_applicable, llm_diagnose, quick_diagnose
from .governance import COOLDOWN_AFTER_APPLY_RUNS
from .post_mortem import schedule_post_mortem_due


async def assert_meta_agent_cooldown(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
) -> None:
    """Require at least COOLDOWN_AFTER_APPLY_RUNS successful runs since last auto-apply."""
    last_applied = (
        await db.execute(
            select(AgentProposal)
            .where(
                AgentProposal.tenant_id == tenant_id,
                AgentProposal.line_item_id == line_item_id,
                AgentProposal.status == "applied",
                AgentProposal.applied_at.is_not(None),
            )
            .order_by(AgentProposal.applied_at.desc())
            .limit(1),
        )
    ).scalar_one_or_none()
    if last_applied is None or last_applied.applied_at is None:
        return

    runs_since = (
        await db.execute(
            select(func.count())
            .select_from(Run)
            .where(
                Run.tenant_id == tenant_id,
                Run.line_item_id == line_item_id,
                Run.status == "succeeded",
                Run.completed_at.is_not(None),
                Run.completed_at > last_applied.applied_at,
            ),
        )
    ).scalar_one() or 0

    if runs_since < COOLDOWN_AFTER_APPLY_RUNS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Meta-agent in cooldown: attendi {COOLDOWN_AFTER_APPLY_RUNS - runs_since} "
                f"run di osservazione prima di una nuova proposta automatica"
            ),
        )


async def load_context(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
) -> dict[str, Any]:
    setting = (
        await db.execute(select(Setting).where(Setting.tenant_id == tenant_id).limit(1))
    ).scalar_one_or_none()

    runs = (
        await db.execute(
            select(Run)
            .where(Run.tenant_id == tenant_id, Run.line_item_id == line_item_id)
            .order_by(Run.started_at.desc())
            .limit(8),
        )
    ).scalars().all()

    run_ids = [r.id for r in runs]
    decisions: list[Decision] = []
    if run_ids:
        decisions = list(
            (
                await db.execute(
                    select(Decision)
                    .where(Decision.run_id.in_(run_ids))
                    .order_by(Decision.created_at.desc())
                    .limit(50),
                )
            ).scalars().all(),
        )

    strategy = await get_strategy_for_scope(
        db, tenant_id=tenant_id, line_item_id=line_item_id,
    )
    if strategy is None:
        strategy = await get_strategy_for_scope(db, tenant_id=tenant_id, line_item_id=None)

    constraints: list[HardConstraint] = []
    if strategy:
        constraints = await list_constraints(
            db, tenant_id=tenant_id, strategy_id=strategy.id,
        )

    funnel = await get_action_funnel(db, tenant_id=tenant_id)

    return {
        "settings": snapshot_row(setting) if setting else {},
        "runs": [snapshot_row(r) for r in runs],
        "recent_decisions": [snapshot_row(d) for d in decisions],
        "strategy": snapshot_row(strategy) if strategy else None,
        "constraints": [snapshot_row(c) for c in constraints],
        "actions": [snapshot_row(a) for a in funnel],
    }


async def create_proposal_from_brief(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    brief: str,
    user_id: str | None = None,
) -> AgentProposal:
    item = await db.get(LineItem, line_item_id)
    if item is None or item.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")

    await assert_meta_agent_cooldown(db, tenant_id=tenant_id, line_item_id=line_item_id)

    context = await load_context(db, tenant_id=tenant_id, line_item_id=line_item_id)
    result = quick_diagnose(context, brief)
    if result is None:
        result = await llm_diagnose(context, brief)

    changes = result.get("proposed_changes") or []
    auto = is_auto_applicable(changes)

    proposal = AgentProposal(
        tenant_id=tenant_id,
        agent_type="tuning",
        line_item_id=line_item_id,
        brief=brief,
        diagnosis=result.get("diagnosis"),
        proposed_changes=changes,
        expected_impact=result.get("expected_impact"),
        status="pending",
        auto_applicable=auto,
    )
    db.add(proposal)
    await db.flush()

    if auto and changes:
        await apply_proposed_changes(
            db,
            tenant_id=tenant_id,
            changes=changes,
            actor_type="tuning_agent",
            user_id=user_id,
            proposal_id=proposal.id,
        )
        proposal.status = "applied"
        proposal.applied_at = utcnow()
        proposal.post_mortem_due_at = utcnow() + schedule_post_mortem_due()

    await db.refresh(proposal)
    return proposal
