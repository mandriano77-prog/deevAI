"""Structural validation for Setup Agent proposed changes."""

from __future__ import annotations

from typing import Any

ALLOWED_ENTITIES = frozenset({
    "optimization_strategy",
    "optimization_strategies",
    "action",
    "actions",
    "hard_constraint",
    "hard_constraints",
    "settings",
})
ALLOWED_OPERATIONS = frozenset({"create", "update"})


def validate_changes(changes: list[dict[str, Any]]) -> None:
    if not changes:
        raise ValueError("proposed_changes cannot be empty for setup")
    for ch in changes:
        entity = ch.get("entity", "")
        if entity not in ALLOWED_ENTITIES:
            raise ValueError(f"Invalid entity: {entity}")
        if ch.get("operation") not in ALLOWED_OPERATIONS:
            raise ValueError(f"Invalid operation: {ch.get('operation')}")
        if ch.get("operation") == "delete":
            raise ValueError("Setup agent cannot propose delete operations")
        if "payload" not in ch and "field" not in ch:
            raise ValueError("Each change needs payload or field")
