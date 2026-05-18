"""Optimization strategies and hard constraints."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from ..routing import CamelCaseRouter
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id, get_optional_user_id
from ..services.audit import snapshot_row, write_audit
from ..models import HardConstraint, OptimizationStrategy
from ..schemas.hard_constraint import HardConstraintCreate, HardConstraintRead, HardConstraintUpdate
from ..schemas.optimization_strategy import (
    OptimizationStrategyCreate,
    OptimizationStrategyRead,
)
from ..services.optimization import (
    DEFAULT_SCOPE,
    get_strategy_for_scope,
    list_constraints,
    parse_strategy_scope,
    require_line_item,
    require_strategy,
)

strategies_router = CamelCaseRouter(
    prefix="/optimization-strategies",
    tags=["optimization-strategies"],
)
constraints_router = CamelCaseRouter(prefix="/constraints", tags=["constraints"])


@strategies_router.get("/{line_item_id_or_default}", response_model=OptimizationStrategyRead)
async def get_optimization_strategy(
    line_item_id_or_default: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> OptimizationStrategy:
    line_item_id = parse_strategy_scope(line_item_id_or_default)
    if line_item_id is not None:
        await require_line_item(db, tenant_id=tenant_id, line_item_id=line_item_id)

    strategy = await get_strategy_for_scope(
        db, tenant_id=tenant_id, line_item_id=line_item_id,
    )
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Optimization strategy not found",
        )
    return strategy


@strategies_router.put("/{line_item_id_or_default}", response_model=OptimizationStrategyRead)
async def upsert_optimization_strategy(
    line_item_id_or_default: str,
    payload: OptimizationStrategyCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> OptimizationStrategy:
    line_item_id = parse_strategy_scope(line_item_id_or_default)
    if line_item_id is not None:
        await require_line_item(db, tenant_id=tenant_id, line_item_id=line_item_id)
    elif payload.line_item_id is not None:
        line_item_id = payload.line_item_id
        await require_line_item(db, tenant_id=tenant_id, line_item_id=line_item_id)

    strategy = await get_strategy_for_scope(
        db, tenant_id=tenant_id, line_item_id=line_item_id,
    )
    data = payload.model_dump()
    data["line_item_id"] = line_item_id

    before = snapshot_row(strategy) if strategy else None
    if strategy is None:
        strategy = OptimizationStrategy(tenant_id=tenant_id, **data)
        db.add(strategy)
        action = "create"
    else:
        for key, value in data.items():
            setattr(strategy, key, value)
        action = "update"

    await db.flush()
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="optimization_strategies",
        entity_id=strategy.id,
        action=action,
        before=before,
        after=snapshot_row(strategy),
    )
    await db.refresh(strategy)
    return strategy


@strategies_router.delete(
    "/{line_item_id_or_default}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_optimization_strategy(
    line_item_id_or_default: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> None:
    line_item_id = parse_strategy_scope(line_item_id_or_default)
    strategy = await get_strategy_for_scope(
        db, tenant_id=tenant_id, line_item_id=line_item_id,
    )
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Optimization strategy not found",
        )
    before = snapshot_row(strategy)
    strategy.status = "archived"
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="optimization_strategies",
        entity_id=strategy.id,
        action="delete",
        before=before,
        after=snapshot_row(strategy),
    )
    await db.flush()


@strategies_router.get(
    "/{strategy_id}/constraints",
    response_model=list[HardConstraintRead],
)
async def list_strategy_constraints(
    strategy_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> list[HardConstraint]:
    return await list_constraints(db, tenant_id=tenant_id, strategy_id=strategy_id)


@strategies_router.post(
    "/{strategy_id}/constraints",
    response_model=HardConstraintRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_constraint(
    strategy_id: str,
    payload: HardConstraintCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> HardConstraint:
    await require_strategy(db, tenant_id=tenant_id, strategy_id=strategy_id)
    constraint = HardConstraint(
        tenant_id=tenant_id,
        optimization_strategy_id=strategy_id,
        **payload.model_dump(),
    )
    db.add(constraint)
    await db.flush()
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="hard_constraints",
        entity_id=constraint.id,
        action="create",
        before=None,
        after=snapshot_row(constraint),
    )
    await db.refresh(constraint)
    return constraint


@constraints_router.patch("/{constraint_id}", response_model=HardConstraintRead)
async def update_constraint(
    constraint_id: str,
    payload: HardConstraintUpdate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> HardConstraint:
    constraint = await db.get(HardConstraint, constraint_id)
    if constraint is None or constraint.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Constraint not found",
        )

    before = snapshot_row(constraint)
    updates = payload.model_dump(exclude_unset=True)
    metric = updates.get("metric", constraint.metric)
    operator = updates.get("operator", constraint.operator)
    value = updates.get("value", constraint.value)

    if "metric" in updates or "operator" in updates:
        from ..schemas.hard_constraint import validate_metric_operator

        validate_metric_operator(metric, operator)
    if "value" in updates:
        from ..schemas.hard_constraint import validate_metric_value

        validate_metric_value(metric, float(value))

    for key, val in updates.items():
        setattr(constraint, key, val)
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="hard_constraints",
        entity_id=constraint.id,
        action="update",
        before=before,
        after=snapshot_row(constraint),
    )
    await db.flush()
    await db.refresh(constraint)
    return constraint


@constraints_router.delete("/{constraint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_constraint(
    constraint_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> None:
    constraint = await db.get(HardConstraint, constraint_id)
    if constraint is None or constraint.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Constraint not found",
        )
    before = snapshot_row(constraint)
    constraint.status = "archived"
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="hard_constraints",
        entity_id=constraint.id,
        action="delete",
        before=before,
        after=snapshot_row(constraint),
    )
    await db.flush()


__all__ = ["strategies_router", "constraints_router", "DEFAULT_SCOPE"]
