"""Setup Agent pipeline — brief → AgentProposal (always approval-required)."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import AgentProposal, LineItem
from ..meta_agent.runner import load_context


def _parse_setup_output(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
    return json.loads(cleaned)


async def run_setup_agent(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    brief: str,
    user_id: str | None = None,
) -> AgentProposal:
    item = await db.get(LineItem, line_item_id)
    if item is None or item.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")

    context = await load_context(db, tenant_id=tenant_id, line_item_id=line_item_id)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY not configured",
        )

    from anthropic import Anthropic

    from .prompts import SETUP_PROMPT

    client = Anthropic(api_key=api_key, timeout=30.0, max_retries=2)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            system=SETUP_PROMPT,
            messages=[{
                "role": "user",
                "content": json.dumps({"context": context, "brief": brief}),
            }],
        )
    except Exception as exc:
        if "429" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM rate limited",
                headers={"Retry-After": "60"},
            ) from exc
        raise

    parsed = _parse_setup_output(response.content[0].text)
    changes = parsed.get("proposed_changes") or []
    from .validate import validate_changes

    validate_changes(changes)

    proposal = AgentProposal(
        tenant_id=tenant_id,
        agent_type="setup",
        line_item_id=line_item_id,
        brief=brief,
        diagnosis=parsed.get("diagnosis"),
        proposed_changes=changes,
        expected_impact=parsed.get("expected_impact"),
        status="pending",
        auto_applicable=False,
        llm_model="claude-sonnet-4-6",
        llm_input_tokens=getattr(response.usage, "input_tokens", None),
        llm_output_tokens=getattr(response.usage, "output_tokens", None),
    )
    db.add(proposal)
    await db.flush()
    await db.refresh(proposal)
    return proposal
