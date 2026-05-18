"""Action funnel helpers — shared by API routes and seed."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Action


async def set_action_funnel(
    db: AsyncSession,
    *,
    tenant_id: str,
    ordered_action_ids: list[str],
) -> list[Action]:
    """Wire actions into a linear funnel (position 1 = root, no parent)."""
    if not ordered_action_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ordered_action_ids must not be empty",
        )

    result = await db.execute(
        select(Action).where(
            Action.tenant_id == tenant_id,
            Action.id.in_(ordered_action_ids),
            Action.status != "archived",
        ),
    )
    by_id = {a.id: a for a in result.scalars().all()}
    missing = [aid for aid in ordered_action_ids if aid not in by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown action ids: {missing}",
        )

    parent_id: str | None = None
    ordered: list[Action] = []
    for position, action_id in enumerate(ordered_action_ids, start=1):
        action = by_id[action_id]
        action.funnel_position = position
        action.funnel_parent_id = parent_id
        parent_id = action.id
        ordered.append(action)

    await db.flush()
    return ordered


async def get_action_funnel(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str | None = None,
) -> list[Action]:
    """Return tenant-global (or line-item) funnel steps ordered by position."""
    stmt = select(Action).where(
        Action.tenant_id == tenant_id,
        Action.status != "archived",
        Action.funnel_position.is_not(None),
    )
    if line_item_id is None:
        stmt = stmt.where(Action.line_item_id.is_(None))
    else:
        stmt = stmt.where(Action.line_item_id == line_item_id)

    result = await db.execute(stmt.order_by(Action.funnel_position.asc()))
    return list(result.scalars().all())
