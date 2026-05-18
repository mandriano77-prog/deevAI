"""Meta-agent proposals and brief submission."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status

from ..routing import CamelCaseRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id, get_optional_user_id
from ..models import AgentProposal, utcnow
from ..schemas.meta_agent import MetaAgentBriefIn, AgentProposalRead
from ..services.meta_agent.apply import apply_proposed_changes
from ..services.meta_agent.runner import create_proposal_from_brief
line_items_router = CamelCaseRouter(tags=["meta-agent"])
proposals_router = CamelCaseRouter(prefix="/meta-agent/proposals", tags=["tuning-agent"])


@line_items_router.post(
    "/line-items/{line_item_id}/tuning-agent/brief",
    response_model=AgentProposalRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_brief(
    line_item_id: str,
    payload: MetaAgentBriefIn,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> AgentProposal:
    return await create_proposal_from_brief(
        db,
        tenant_id=tenant_id,
        line_item_id=line_item_id,
        brief=payload.brief,
        user_id=user_id,
    )


@proposals_router.get("", response_model=list[AgentProposalRead])
async def list_proposals(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status_filter: str | None = Query(default=None, alias="status"),
    line_item_id: str | None = Query(default=None),
) -> list[AgentProposal]:
    stmt = select(AgentProposal).where(AgentProposal.tenant_id == tenant_id)
    if status_filter:
        stmt = stmt.where(AgentProposal.status == status_filter)
    if line_item_id:
        stmt = stmt.where(AgentProposal.line_item_id == line_item_id)
    result = await db.execute(stmt.order_by(AgentProposal.created_at.desc()))
    return list(result.scalars().all())


async def _get_proposal(
    db: AsyncSession, tenant_id: str, proposal_id: str,
) -> AgentProposal:
    proposal = await db.get(AgentProposal, proposal_id)
    if proposal is None or proposal.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


@proposals_router.post("/{proposal_id}/approve", response_model=AgentProposalRead)
async def approve_proposal(
    proposal_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> AgentProposal:
    proposal = await _get_proposal(db, tenant_id, proposal_id)
    if proposal.status not in ("pending",):
        raise HTTPException(status_code=400, detail="Proposal not pending")
    proposal.status = "approved"
    proposal.approver_user_id = user_id
    proposal.approved_at = utcnow()
    await apply_proposed_changes(
        db,
        tenant_id=tenant_id,
        changes=proposal.proposed_changes,
        user_id=user_id,
        actor_type="user",
    )
    proposal.status = "applied"
    proposal.applied_at = utcnow()
    from ..services.meta_agent.post_mortem import schedule_post_mortem_due
    proposal.post_mortem_due_at = utcnow() + schedule_post_mortem_due()
    await db.flush()
    await db.refresh(proposal)
    return proposal


@proposals_router.post("/{proposal_id}/reject", response_model=AgentProposalRead)
async def reject_proposal(
    proposal_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> AgentProposal:
    proposal = await _get_proposal(db, tenant_id, proposal_id)
    if proposal.status != "pending":
        raise HTTPException(status_code=400, detail="Proposal not pending")
    proposal.status = "rejected"
    await db.flush()
    await db.refresh(proposal)
    return proposal


@proposals_router.post("/{proposal_id}/revert", response_model=AgentProposalRead)
async def revert_proposal(
    proposal_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> AgentProposal:
    proposal = await _get_proposal(db, tenant_id, proposal_id)
    if proposal.status != "applied":
        raise HTTPException(status_code=400, detail="Only applied proposals can be reverted")
    revert_changes = []
    for ch in proposal.proposed_changes:
        revert_changes.append({
            **ch,
            "from": ch.get("to"),
            "to": ch.get("from"),
            "reason": "revert",
        })
    await apply_proposed_changes(
        db, tenant_id=tenant_id, changes=revert_changes, user_id=user_id,
    )
    proposal.status = "reverted"
    await db.flush()
    await db.refresh(proposal)
    return proposal
