"""Meta-agent proposal schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .base import ApiModel

ProposalStatus = Literal["pending", "approved", "rejected", "applied", "reverted"]


class MetaAgentBriefIn(ApiModel):
    brief: str = Field(min_length=3, max_length=4000)


class ProposedChange(ApiModel):
    entity: str
    entity_id: str
    field: str
    from_value: Any = Field(alias="from")
    to_value: Any = Field(alias="to")
    reason: str

    model_config = {"populate_by_name": True}


class AgentProposalRead(ApiModel):
    id: str
    tenant_id: str
    agent_type: str
    line_item_id: str | None
    brief: str
    diagnosis: str | None
    proposed_changes: list[dict[str, Any]]
    expected_impact: dict[str, Any] | None
    status: ProposalStatus
    auto_applicable: bool
    approver_user_id: str | None
    approved_at: datetime | None
    applied_at: datetime | None
    reverted_at: datetime | None
    post_mortem_due_at: datetime | None
    llm_model: str | None
    llm_input_tokens: int | None
    llm_output_tokens: int | None
    post_mortem: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


MetaAgentProposalRead = AgentProposalRead

