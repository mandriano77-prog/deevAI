"""Build-line-item context for M.AI — injected into the Claude user message."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import (
    Action,
    AgentProposal,
    HardConstraint,
    LineItem,
    OptimizationStrategy,
    Run,
    Setting,
)
from ...services.audit import snapshot_row
from ...services.optimization import get_strategy_for_scope, list_constraints


def _float(val: Decimal | float | int | None) -> float | None:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


def compute_metrics_summary(runs_recent: list[dict[str, Any]]) -> dict[str, Any]:
    """Derived KPI hints from recent Run snapshots (JSON-safe dicts)."""
    if not runs_recent:
        return {}

    last = runs_recent[0]
    movement_rates: list[float] = []
    for r in runs_recent[:3]:
        nd = int(r.get("n_decisions") or 0)
        np = int(r.get("n_changes_proposed") or 0)
        movement_rates.append(np / max(nd, 1))
    avg_movement = sum(movement_rates) / len(movement_rates) if movement_rates else 0.0

    # Simple oscillation proxy: variance of blended CPV across runs
    cpvs = [_float(r.get("blended_cpv_observed")) for r in runs_recent[:4]]
    cpvs_f = [c for c in cpvs if c is not None]
    oscillation = 0.0
    if len(cpvs_f) >= 2:
        mean = sum(cpvs_f) / len(cpvs_f)
        oscillation = (
            sum(abs(c - mean) for c in cpvs_f) / len(cpvs_f) / mean if mean > 0 else 0.0
        )

    return {
        "last_run_week_label": last.get("week_label"),
        "last_blended_cpv_observed": last.get("blended_cpv_observed"),
        "last_blended_roas": last.get("blended_roas"),
        "last_blended_visits": last.get("blended_visits"),
        "last_n_changes_proposed": last.get("n_changes_proposed"),
        "last_n_decisions": last.get("n_decisions"),
        "movement_rate_avg_last_3_runs": round(avg_movement, 4),
        "cpv_oscillation_index": round(float(oscillation), 4),
    }


def _serialize_strategy(row: OptimizationStrategy | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return snapshot_row(row)


def _serialize_proposal_short(p: AgentProposal) -> dict[str, Any]:
    return {
        "id": p.id,
        "agent_type": p.agent_type,
        "status": p.status,
        "brief": (p.brief[:200] + "…") if len(p.brief) > 200 else p.brief,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def build_mai_context(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
) -> dict[str, Any]:
    item = await db.get(LineItem, line_item_id)
    if item is None or item.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Line item not found",
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

    actions = (
        await db.execute(
            select(Action).where(
                Action.tenant_id == tenant_id,
                Action.status == "active",
                or_(
                    Action.line_item_id == line_item_id,
                    Action.line_item_id.is_(None),
                ),
            ),
        )
    ).scalars().all()

    runs = (
        await db.execute(
            select(Run)
            .where(Run.tenant_id == tenant_id, Run.line_item_id == line_item_id)
            .order_by(Run.window_end.desc())
            .limit(8),
        )
    ).scalars().all()

    pending = (
        await db.execute(
            select(AgentProposal)
            .where(
                AgentProposal.tenant_id == tenant_id,
                AgentProposal.line_item_id == line_item_id,
                AgentProposal.status == "pending",
            )
            .order_by(AgentProposal.created_at.desc())
            .limit(5),
        )
    ).scalars().all()

    setting = (
        await db.execute(select(Setting).where(Setting.tenant_id == tenant_id).limit(1))
    ).scalar_one_or_none()

    runs_data = [snapshot_row(r) for r in runs]

    return {
        "line_item": {
            "id": item.id,
            "name": item.name,
            "mode": item.mode,
            "cpv_target_legacy": _float(item.cpv_target),
            "current_max_bid": _float(item.current_max_bid),
            "status": item.status,
        },
        "tenant_settings": snapshot_row(setting) if setting else {},
        "strategy": _serialize_strategy(strategy),
        "constraints": [snapshot_row(c) for c in constraints],
        "actions": [snapshot_row(a) for a in actions],
        "runs_recent": runs_data,
        "metrics_summary": compute_metrics_summary(runs_data),
        "proposals_pending": [_serialize_proposal_short(p) for p in pending],
    }
