"""Validate Claude JSON for M.AI."""

from __future__ import annotations

from typing import Any

from ...schemas.mai import MaiAskOut


def validate_mai_ask_response(parsed: dict[str, Any]) -> MaiAskOut:
    return MaiAskOut.model_validate(parsed)


EXECUTABLE_INTENTS = frozenset({
    "setup.brief",
    "tuning.brief",
    "proposal.approve",
    "proposal.apply",
    "proposal.reject",
    "proposal.revert",
})
