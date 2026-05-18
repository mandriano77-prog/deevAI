"""Post-mortem job for applied meta-agent proposals (7-day review)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import AgentProposal, Run, utcnow


async def run_due_post_mortems(session: AsyncSession) -> int:
    """Evaluate proposals past post_mortem_due_at. Returns count processed."""
    now = utcnow()
    result = await session.execute(
        select(AgentProposal).where(
            AgentProposal.applied_at.is_not(None),
            AgentProposal.post_mortem_due_at <= now,
            AgentProposal.post_mortem.is_(None),
        ),
    )
    proposals = list(result.scalars().all())
    processed = 0

    for proposal in proposals:
        expected = proposal.expected_impact or {}
        actual: dict = {"blended_cpv_observed": None, "blended_visits": None}

        if proposal.line_item_id:
            runs = (
                await session.execute(
                    select(Run)
                    .where(
                        Run.line_item_id == proposal.line_item_id,
                        Run.tenant_id == proposal.tenant_id,
                        Run.status == "succeeded",
                    )
                    .order_by(Run.completed_at.desc())
                    .limit(2),
                )
            ).scalars().all()
            if runs:
                actual["blended_cpv_observed"] = float(runs[0].blended_cpv_observed or 0)
                actual["blended_visits"] = runs[0].blended_visits

        exp_cpv_delta = expected.get("primary_objective_delta_pct")
        verdict = "partial"
        if not expected or exp_cpv_delta is None:
            verdict = "partial"
        elif actual["blended_cpv_observed"] is not None:
            verdict = "match" if abs(exp_cpv_delta) < 15 else "miss"

        proposal.post_mortem = {
            "actual_impact": actual,
            "delta_vs_expected": {
                "primary_objective_delta_pct": exp_cpv_delta,
            },
            "verdict": verdict,
        }
        processed += 1

    if processed:
        await session.flush()
    return processed


def schedule_post_mortem_due() -> timedelta:
    return timedelta(days=7)
