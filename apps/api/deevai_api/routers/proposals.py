"""Unified proposal approve / reject / apply / revert."""

from __future__ import annotations

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id, get_optional_user_id
from ..models import AgentProposal
from ..routing import CamelCaseRouter
from ..schemas.meta_agent import MetaAgentProposalRead
from ..services.agent_proposal_lifecycle import (
    approve_agent_proposal,
    apply_agent_proposal_by_id,
    reject_agent_proposal,
    revert_agent_proposal,
)

router = CamelCaseRouter(prefix="/proposals", tags=["proposals"])


@router.get("", response_model=list[MetaAgentProposalRead])
async def list_proposals(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    agent_type: str | None = Query(default=None, alias="agent_type"),
    status_filter: str | None = Query(default=None, alias="status"),
    line_item_id: str | None = Query(default=None),
) -> list[AgentProposal]:
    stmt = select(AgentProposal).where(AgentProposal.tenant_id == tenant_id)
    if agent_type:
        stmt = stmt.where(AgentProposal.agent_type == agent_type)
    if status_filter:
        stmt = stmt.where(AgentProposal.status == status_filter)
    if line_item_id:
        stmt = stmt.where(AgentProposal.line_item_id == line_item_id)
    result = await db.execute(stmt.order_by(AgentProposal.created_at.desc()))
    return list(result.scalars().all())


@router.post("/{proposal_id}/approve", response_model=MetaAgentProposalRead)
async def approve_proposal(
    proposal_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> AgentProposal:
    return await approve_agent_proposal(
        db,
        tenant_id=tenant_id,
        proposal_id=proposal_id,
        user_id=user_id,
    )


@router.post("/{proposal_id}/reject", response_model=MetaAgentProposalRead)
async def reject_proposal(
    proposal_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> AgentProposal:
    return await reject_agent_proposal(db, tenant_id=tenant_id, proposal_id=proposal_id)


@router.post("/{proposal_id}/apply", response_model=MetaAgentProposalRead)
async def apply_proposal(
    proposal_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> AgentProposal:
    return await apply_agent_proposal_by_id(
        db,
        tenant_id=tenant_id,
        proposal_id=proposal_id,
        user_id=user_id,
    )


@router.post("/{proposal_id}/revert", response_model=MetaAgentProposalRead)
async def revert_proposal(
    proposal_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> AgentProposal:
    return await revert_agent_proposal(
        db,
        tenant_id=tenant_id,
        proposal_id=proposal_id,
        max_age_days=None,
    )
