"""Persist M.AI interactions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import MaiLog, new_uuid


async def log_mai_interaction(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str | None,
    line_item_id: str | None,
    prompt: str | None,
    intent: str | None,
    proposal: dict[str, Any] | None,
    action: str,
    payload: dict[str, Any] | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> MaiLog:
    row = MaiLog(
        id=new_uuid(),
        tenant_id=tenant_id,
        user_id=user_id,
        line_item_id=line_item_id,
        prompt=prompt,
        intent=intent,
        proposal=proposal,
        action=action,
        payload=payload,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    db.add(row)
    await db.flush()
    return row


async def list_mai_log(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str | None,
    limit: int,
) -> list[MaiLog]:
    stmt = select(MaiLog).where(MaiLog.tenant_id == tenant_id)
    if line_item_id:
        stmt = stmt.where(MaiLog.line_item_id == line_item_id)
    stmt = stmt.order_by(MaiLog.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
