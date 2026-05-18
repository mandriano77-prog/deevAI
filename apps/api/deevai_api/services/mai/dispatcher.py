"""Dispatch POST /v1/mai/execute."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent_proposal_lifecycle import (
    approve_agent_proposal,
    apply_agent_proposal_by_id,
    reject_agent_proposal,
    revert_agent_proposal,
)
from ..meta_agent.runner import create_proposal_from_brief
from ..setup_agent.pipeline import run_setup_agent
from .validator import EXECUTABLE_INTENTS


async def dispatch_mai_execute(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: str | None,
    intent: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if intent not in EXECUTABLE_INTENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Intent non eseguibile: {intent}",
        )

    if intent == "setup.brief":
        line_item_id = payload.get("line_item_id")
        brief = payload.get("brief")
        if not line_item_id or not brief:
            raise HTTPException(422, "line_item_id e brief richiesti")
        prop = await run_setup_agent(
            db,
            tenant_id=tenant_id,
            line_item_id=str(line_item_id),
            brief=str(brief),
            user_id=user_id,
        )
        return {
            "success": True,
            "message": "Setup Agent avviato. Trovi la proposta nello stato pending.",
            "data": {"proposal_id": prop.id, "status": prop.status},
        }

    if intent == "tuning.brief":
        line_item_id = payload.get("line_item_id")
        brief = payload.get("brief")
        if not line_item_id or not brief:
            raise HTTPException(422, "line_item_id e brief richiesti")
        prop = await create_proposal_from_brief(
            db,
            tenant_id=tenant_id,
            line_item_id=str(line_item_id),
            brief=str(brief),
            user_id=user_id,
        )
        return {
            "success": True,
            "message": "Tuning Agent elaborato. Controlla la nuova proposta.",
            "data": {"proposal_id": prop.id, "status": prop.status},
        }

    proposal_id = payload.get("proposal_id")
    if not proposal_id:
        raise HTTPException(422, "proposal_id richiesto")

    from ...models import AgentProposal

    prop_check = await db.get(AgentProposal, str(proposal_id))
    if prop_check is None or prop_check.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if intent == "proposal.approve":
        prop = await approve_agent_proposal(
            db,
            tenant_id=tenant_id,
            proposal_id=str(proposal_id),
            user_id=user_id,
        )
        return {
            "success": True,
            "message": "Proposta approvata.",
            "data": {"proposal_id": prop.id, "status": prop.status},
        }

    if intent == "proposal.reject":
        prop = await reject_agent_proposal(
            db,
            tenant_id=tenant_id,
            proposal_id=str(proposal_id),
        )
        return {
            "success": True,
            "message": "Proposta rifiutata.",
            "data": {"proposal_id": prop.id, "status": prop.status},
        }

    if intent == "proposal.apply":
        prop = await apply_agent_proposal_by_id(
            db,
            tenant_id=tenant_id,
            proposal_id=str(proposal_id),
            user_id=user_id,
        )
        return {
            "success": True,
            "message": "Proposta applicata.",
            "data": {"proposal_id": prop.id, "status": prop.status},
        }

    if intent == "proposal.revert":
        prop = await revert_agent_proposal(
            db,
            tenant_id=tenant_id,
            proposal_id=str(proposal_id),
            max_age_days=7,
        )
        return {
            "success": True,
            "message": "Proposta annullata (revert).",
            "data": {"proposal_id": prop.id, "status": prop.status},
        }
