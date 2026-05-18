"""Route proposal apply to Setup vs Tuning appliers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentProposal
from .meta_agent.apply import apply_proposed_changes
from .meta_agent.post_mortem import schedule_post_mortem_due
from .setup_agent.applier import apply_proposal as apply_setup_proposal
from ..models import utcnow


def _is_legacy_tuning_change(change: dict) -> bool:
    return "field" in change and "operation" not in change


async def apply_agent_proposal(
    db: AsyncSession,
    *,
    proposal: AgentProposal,
    user_id: str | None,
) -> AgentProposal:
    if proposal.agent_type == "setup":
        if proposal.status != "approved":
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="Setup proposals must be approved first")
        return await apply_setup_proposal(db, proposal_id=proposal.id, user_id=user_id)

    actor = "tuning_agent"
    changes = proposal.proposed_changes or []
    if changes and not _is_legacy_tuning_change(changes[0]):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail="Tuning agent expects legacy field-based proposed_changes",
        )

    await apply_proposed_changes(
        db,
        tenant_id=proposal.tenant_id,
        changes=changes,
        actor_type=actor,
        user_id=user_id,
        proposal_id=proposal.id,
    )
    proposal.status = "applied"
    proposal.applied_at = utcnow()
    proposal.post_mortem_due_at = utcnow() + schedule_post_mortem_due()
    await db.flush()
    return proposal
