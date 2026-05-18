"""Apply meta-agent proposed changes to domain models."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Action, Setting
from ...services.audit import snapshot_row, write_audit
from .governance import validate_proposed_changes


async def apply_proposed_changes(
    db: AsyncSession,
    *,
    tenant_id: str,
    changes: list[dict[str, Any]],
    actor_type: str = "tuning_agent",
    user_id: str | None = None,
    proposal_id: str | None = None,
) -> None:
    errors = validate_proposed_changes(changes)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(errors),
        )

    for ch in changes:
        entity = ch["entity"]
        entity_id = ch["entity_id"]
        field = ch["field"]
        new_value = ch["to"]

        if entity == "settings":
            row = await db.get(Setting, entity_id)
            if row is None or row.tenant_id != tenant_id:
                raise HTTPException(status_code=404, detail="Setting not found")
            before = snapshot_row(row)
            setattr(row, field, new_value)
            await write_audit(
                db,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                actor_type=actor_type,
                entity="settings",
                entity_id=entity_id,
                action="apply",
                before=before,
                after=snapshot_row(row),
                proposal_id=proposal_id,
            )
        elif entity == "actions":
            row = await db.get(Action, entity_id)
            if row is None or row.tenant_id != tenant_id:
                raise HTTPException(status_code=404, detail="Action not found")
            before = snapshot_row(row)
            setattr(row, field, new_value)
            await write_audit(
                db,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                actor_type=actor_type,
                entity="actions",
                entity_id=entity_id,
                action="apply",
                before=before,
                after=snapshot_row(row),
                proposal_id=proposal_id,
            )
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported entity for apply: {entity}",
            )
    await db.flush()
