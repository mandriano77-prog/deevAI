"""Pydantic schemas for M.AI APIs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ApiModel


class MaiAskIn(ApiModel):
    prompt: str = Field(min_length=1, max_length=8000)
    line_item_id: str = Field(min_length=1, max_length=36)


class MaiPreviewOut(ApiModel):
    summary: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MaiAskOut(ApiModel):
    intent: str = Field(min_length=1, max_length=80)
    type: Literal["query", "brief", "govern", "system"]
    preview: MaiPreviewOut
    payload: dict[str, Any] | None = None
    answer: str | None = None

    @model_validator(mode="after")
    def payload_rules(self) -> MaiAskOut:
        if self.type in ("brief", "govern") and self.payload is None:
            raise ValueError("payload richiesto per brief/govern")
        return self


class MaiExecuteIn(ApiModel):
    intent: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class MaiExecuteOut(ApiModel):
    success: bool
    message: str
    data: dict[str, Any] | None = None


class MaiLogItem(ApiModel):
    id: str
    line_item_id: str | None
    prompt: str | None
    intent: str | None
    action: str
    proposal: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: str


class MaiHistoryOut(ApiModel):
    items: list[MaiLogItem]
