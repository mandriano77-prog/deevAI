"""Optimization strategy resolution — tenant default vs line-item override."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import HardConstraint, LineItem, OptimizationStrategy

DEFAULT_SCOPE = "default"


def parse_strategy_scope(line_item_id_or_default: str) -> str | None:
    """Return line_item_id, or None for tenant default."""
    if line_item_id_or_default == DEFAULT_SCOPE:
        return None
    return line_item_id_or_default


async def get_strategy_for_scope(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str | None,
) -> OptimizationStrategy | None:
    stmt = select(OptimizationStrategy).where(
        OptimizationStrategy.tenant_id == tenant_id,
    )
    if line_item_id is None:
        stmt = stmt.where(OptimizationStrategy.line_item_id.is_(None))
    else:
        stmt = stmt.where(OptimizationStrategy.line_item_id == line_item_id)

    return (await db.execute(stmt)).scalar_one_or_none()


async def resolve_effective_strategy(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
) -> OptimizationStrategy | None:
    """Line-item override first, then tenant default. None → legacy CPV-only path."""
    item_strategy = await get_strategy_for_scope(
        db, tenant_id=tenant_id, line_item_id=line_item_id,
    )
    if item_strategy is not None:
        return item_strategy
    return await get_strategy_for_scope(db, tenant_id=tenant_id, line_item_id=None)


async def require_strategy(
    db: AsyncSession,
    *,
    tenant_id: str,
    strategy_id: str,
) -> OptimizationStrategy:
    strategy = await db.get(OptimizationStrategy, strategy_id)
    if strategy is None or strategy.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Optimization strategy not found",
        )
    return strategy


async def require_line_item(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
) -> LineItem:
    item = await db.get(LineItem, line_item_id)
    if item is None or item.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Line item not found",
        )
    return item


async def list_constraints(
    db: AsyncSession,
    *,
    tenant_id: str,
    strategy_id: str,
) -> list[HardConstraint]:
    await require_strategy(db, tenant_id=tenant_id, strategy_id=strategy_id)
    result = await db.execute(
        select(HardConstraint).where(
            HardConstraint.tenant_id == tenant_id,
            HardConstraint.optimization_strategy_id == strategy_id,
            HardConstraint.status != "archived",
        ),
    )
    return list(result.scalars().all())
