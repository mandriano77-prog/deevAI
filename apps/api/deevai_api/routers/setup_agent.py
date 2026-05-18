"""Setup Agent — full configuration from a free-form brief."""

from __future__ import annotations

from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id, get_optional_user_id
from ..routing import CamelCaseRouter
from ..schemas.meta_agent import MetaAgentBriefIn, MetaAgentProposalRead
from ..services.setup_agent.pipeline import run_setup_agent

router = CamelCaseRouter(tags=["setup-agent"])


@router.post(
    "/line-items/{line_item_id}/setup-agent/brief",
    response_model=MetaAgentProposalRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_setup_brief(
    line_item_id: str,
    payload: MetaAgentBriefIn,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
):
    return await run_setup_agent(
        db,
        tenant_id=tenant_id,
        line_item_id=line_item_id,
        brief=payload.brief,
        user_id=user_id,
    )
