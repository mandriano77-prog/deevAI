"""Demo seed data — actions funnel for the deevai-demo tenant.

Usage (from apps/api/, venv active, .env loaded):

    python -m deevai_api.seed
"""

from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import select

from .db import session_scope
from .models import Action, HardConstraint, OptimizationStrategy, Tenant
from .services.actions import set_action_funnel

log = logging.getLogger(__name__)
logging.basicConfig(level="INFO", format="%(levelname)s  %(message)s")

DEMO_SLUG = "deevai-demo"

FUNNEL_SPECS: list[dict] = [
    {
        "name": "visita_listing",
        "type": "visit",
        "weight": 1.0,
        "value_eur": 1.0,
        "funnel_position": 1,
    },
    {
        "name": "richiesta_info",
        "type": "lead",
        "weight": 8.0,
        "value_eur": 7.0,
        "funnel_position": 2,
    },
    {
        "name": "appuntamento",
        "type": "lead",
        "weight": 30.0,
        "value_eur": 50.0,
        "funnel_position": 3,
    },
    {
        "name": "preliminare",
        "type": "custom",
        "weight": 100.0,
        "value_eur": 500.0,
        "funnel_position": 4,
    },
]


async def seed_demo_actions(db, tenant_id: str) -> list[Action]:
    """Create the 4-step demo funnel if not already present."""
    existing = (
        await db.execute(
            select(Action).where(
                Action.tenant_id == tenant_id,
                Action.name.in_([s["name"] for s in FUNNEL_SPECS]),
            ),
        )
    ).scalars().all()
    if len(existing) >= len(FUNNEL_SPECS):
        log.info("Demo actions already seeded for tenant %s", tenant_id)
        return await get_demo_funnel(db, tenant_id)

    created: list[Action] = []
    for spec in FUNNEL_SPECS:
        action = Action(
            tenant_id=tenant_id,
            name=spec["name"],
            type=spec["type"],
            weight=spec["weight"],
            value_eur=spec["value_eur"],
            status="active",
        )
        db.add(action)
        created.append(action)
    await db.flush()

    ordered_ids = [a.id for a in created]
    return await set_action_funnel(db, tenant_id=tenant_id, ordered_action_ids=ordered_ids)


async def get_demo_funnel(db, tenant_id: str) -> list[Action]:
    from .services.actions import get_action_funnel

    return await get_action_funnel(db, tenant_id=tenant_id)


async def seed_demo_optimization(db, tenant_id: str) -> OptimizationStrategy:
    existing = (
        await db.execute(
            select(OptimizationStrategy).where(
                OptimizationStrategy.tenant_id == tenant_id,
                OptimizationStrategy.line_item_id.is_(None),
            ),
        )
    ).scalar_one_or_none()
    if existing is not None:
        log.info("Demo optimization strategy already exists")
        return existing

    strategy = OptimizationStrategy(
        tenant_id=tenant_id,
        mode="blended_2",
        primary_metric="cpa",
        primary_target=4.50,
        primary_weight=70.0,
        secondary_metric="cpc",
        secondary_target=0.10,
        secondary_weight=30.0,
        tolerance_band=0.20,
        status="active",
    )
    db.add(strategy)
    await db.flush()

    constraints = [
        HardConstraint(
            tenant_id=tenant_id,
            optimization_strategy_id=strategy.id,
            metric="cpc",
            operator="lte",
            value=0.15,
            violation_policy="freeze",
        ),
        HardConstraint(
            tenant_id=tenant_id,
            optimization_strategy_id=strategy.id,
            metric="viewability",
            operator="gte",
            value=0.50,
            violation_policy="throttle",
        ),
        HardConstraint(
            tenant_id=tenant_id,
            optimization_strategy_id=strategy.id,
            metric="fraud_rate",
            operator="lte",
            value=0.015,
            violation_policy="kill",
        ),
    ]
    db.add_all(constraints)
    await db.flush()
    return strategy


async def main() -> int:
    async with session_scope() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == DEMO_SLUG))
        ).scalar_one_or_none()
        if tenant is None:
            log.error(
                "Tenant slug=%r not found. Create it first or change DEMO_SLUG.",
                DEMO_SLUG,
            )
            return 1

        funnel = await seed_demo_actions(db, tenant.id)
        log.info("Seeded %d actions for tenant %s", len(funnel), tenant.slug)
        for step in funnel:
            log.info(
                "  %d. %s (weight=%s value=%s€ parent=%s)",
                step.funnel_position,
                step.name,
                step.weight,
                step.value_eur,
                step.funnel_parent_id,
            )

        strategy = await seed_demo_optimization(db, tenant.id)
        log.info(
            "Optimization strategy %s mode=%s primary=%s target=%s",
            strategy.id,
            strategy.mode,
            strategy.primary_metric,
            strategy.primary_target,
        )
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
