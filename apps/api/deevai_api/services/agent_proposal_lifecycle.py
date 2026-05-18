"""Shared AgentProposal lifecycle — used by REST routes and M.AI dispatcher."""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentProposal, utcnow
from .proposals_dispatch import apply_agent_proposal


async def require_agent_proposal(
    db: AsyncSession,
    *,
    tenant_id: str,
    proposal_id: str,
) -> AgentProposal:
    proposal = await db.get(AgentProposal, proposal_id)
    if proposal is None or proposal.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposal not found",
        )
    return proposal


async def approve_agent_proposal(
    db: AsyncSession,
    *,
    tenant_id: str,
    proposal_id: str,
    user_id: str | None,
) -> AgentProposal:
    proposal = await require_agent_proposal(db, tenant_id=tenant_id, proposal_id=proposal_id)
    if proposal.status != "pending":
        raise HTTPException(status_code=422, detail="Only pending proposals can be approved")
    proposal.status = "approved"
    proposal.approver_user_id = user_id
    proposal.approved_at = utcnow()
    await db.flush()
    return proposal


async def reject_agent_proposal(
    db: AsyncSession,
    *,
    tenant_id: str,
    proposal_id: str,
) -> AgentProposal:
    proposal = await require_agent_proposal(db, tenant_id=tenant_id, proposal_id=proposal_id)
    if proposal.status != "pending":
        raise HTTPException(status_code=422, detail="Only pending proposals can be rejected")
    proposal.status = "rejected"
    await db.flush()
    return proposal


async def apply_agent_proposal_by_id(
    db: AsyncSession,
    *,
    tenant_id: str,
    proposal_id: str,
    user_id: str | None,
) -> AgentProposal:
    proposal = await require_agent_proposal(db, tenant_id=tenant_id, proposal_id=proposal_id)
    if proposal.agent_type == "setup" and proposal.status != "approved":
        raise HTTPException(
            status_code=422,
            detail="Setup proposals must be approved before apply",
        )
    if proposal.agent_type == "tuning" and proposal.status not in ("approved", "pending"):
        raise HTTPException(
            status_code=422,
            detail="Tuning proposal must be approved or pending",
        )
    return await apply_agent_proposal(db, proposal=proposal, user_id=user_id)


async def revert_agent_proposal(
    db: AsyncSession,
    *,
    tenant_id: str,
    proposal_id: str,
    max_age_days: int | None = None,
) -> AgentProposal:
    proposal = await require_agent_proposal(db, tenant_id=tenant_id, proposal_id=proposal_id)
    if proposal.status != "applied":
        raise HTTPException(status_code=422, detail="Only applied proposals can be reverted")
    if max_age_days is not None and proposal.applied_at is not None:
        age = utcnow() - proposal.applied_at
        if age > timedelta(days=max_age_days):
            raise HTTPException(
                status_code=422,
                detail=f"Revert window expired ({max_age_days} days)",
            )
    proposal.status = "reverted"
    proposal.reverted_at = utcnow()
    await db.flush()
    return proposal
