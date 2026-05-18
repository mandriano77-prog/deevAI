"""Action catalog and funnel configuration."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from ..routing import CamelCaseRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id, get_optional_user_id
from ..services.audit import snapshot_row, write_audit
from ..models import Action
from ..schemas.action import ActionCreate, ActionFunnelSet, ActionRead, ActionUpdate
from ..services.actions import get_action_funnel, set_action_funnel

router = CamelCaseRouter(prefix="/actions", tags=["actions"])


def _scoped_action(action: Action | None, tenant_id: str) -> Action:
    if action is None or action.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return action


@router.get("", response_model=list[ActionRead])
async def list_actions(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    include_archived: bool = False,
) -> list[Action]:
    stmt = select(Action).where(Action.tenant_id == tenant_id)
    if not include_archived:
        stmt = stmt.where(Action.status != "archived")
    result = await db.execute(stmt.order_by(Action.name))
    return list(result.scalars().all())


@router.get("/funnel", response_model=list[ActionRead])
async def get_funnel(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> list[Action]:
    return await get_action_funnel(db, tenant_id=tenant_id)


@router.post("/funnel", response_model=list[ActionRead])
async def set_funnel(
    payload: ActionFunnelSet,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> list[Action]:
    ordered = await set_action_funnel(
        db, tenant_id=tenant_id, ordered_action_ids=payload.ordered_action_ids,
    )
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="actions",
        entity_id=tenant_id,
        action="update",
        before=None,
        after={"funnel_order": [a.id for a in ordered]},
    )
    return ordered


@router.post("", response_model=ActionRead, status_code=status.HTTP_201_CREATED)
async def create_action(
    payload: ActionCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> Action:
    action = Action(tenant_id=tenant_id, **payload.model_dump())
    db.add(action)
    await db.flush()
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="actions",
        entity_id=action.id,
        action="create",
        before=None,
        after=snapshot_row(action),
    )
    await db.refresh(action)
    return action


@router.patch("/{action_id}", response_model=ActionRead)
async def update_action(
    action_id: str,
    payload: ActionUpdate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> Action:
    action = _scoped_action(await db.get(Action, action_id), tenant_id)
    before = snapshot_row(action)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(action, key, value)
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="actions",
        entity_id=action.id,
        action="update",
        before=before,
        after=snapshot_row(action),
    )
    await db.flush()
    await db.refresh(action)
    return action


@router.delete("/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_action(
    action_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> None:
    action = _scoped_action(await db.get(Action, action_id), tenant_id)
    before = snapshot_row(action)
    action.status = "archived"
    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        actor_type="user",
        entity="actions",
        entity_id=action.id,
        action="delete",
        before=before,
        after=snapshot_row(action),
    )
    await db.flush()
