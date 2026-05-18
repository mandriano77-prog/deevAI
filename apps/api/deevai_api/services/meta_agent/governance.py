"""Governance rules for meta-agent proposed changes."""

from __future__ import annotations

from typing import Any

AUTO_APPLICABLE_ENTITIES = frozenset({"settings"})
AUTO_APPLICABLE_FIELDS: dict[str, frozenset[str]] = {
    "settings": frozenset({
        "max_step_per_run",
        "max_modifier",
        "min_modifier_active",
        "exploration_revive_after_runs",
        "exploration_revive_modifier",
        "min_impressions_for_action",
        "min_visits_for_strong_action",
        "anomalous_ctr_threshold",
        "min_viewability",
    }),
}
NEVER_TOUCH: dict[str, frozenset[str]] = {
    "actions": frozenset({"tracking_source", "dedupe_rule", "type"}),
    "settings": frozenset({"observation_only_until", "default_line_item_mode"}),
}
MAX_CHANGES_PER_PROPOSAL = 2
COOLDOWN_AFTER_APPLY_RUNS = 2


def validate_proposed_changes(changes: list[dict[str, Any]]) -> list[str]:
    """Return list of validation errors (empty = ok)."""
    errors: list[str] = []
    if len(changes) > MAX_CHANGES_PER_PROPOSAL:
        errors.append(f"At most {MAX_CHANGES_PER_PROPOSAL} changes per proposal")

    for ch in changes:
        entity = ch.get("entity", "")
        field = ch.get("field", "")
        blocked = NEVER_TOUCH.get(entity, frozenset())
        if field in blocked:
            errors.append(f"Field {entity}.{field} cannot be modified by meta-agent")

    return errors


def is_auto_applicable(changes: list[dict[str, Any]]) -> bool:
    if not changes:
        return True
    if validate_proposed_changes(changes):
        return False
    for ch in changes:
        entity = ch.get("entity", "")
        field = ch.get("field", "")
        if entity not in AUTO_APPLICABLE_ENTITIES:
            return False
        allowed = AUTO_APPLICABLE_FIELDS.get(entity, frozenset())
        if field not in allowed:
            return False
    return True
