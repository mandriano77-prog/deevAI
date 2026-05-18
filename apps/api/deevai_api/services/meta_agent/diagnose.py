"""Deterministic meta-agent diagnosis patterns."""

from __future__ import annotations

import re
from typing import Any

MAX_STEP_CAP = 0.30


def quick_diagnose(context: dict[str, Any], brief: str) -> dict[str, Any] | None:
    """Return diagnosis dict or None if no pattern matches."""
    brief_l = brief.lower()
    settings = context.get("settings") or {}
    runs: list[dict] = context.get("runs") or []
    decisions: list[dict] = context.get("recent_decisions") or []
    actions: list[dict] = context.get("actions") or []
    constraints: list[dict] = context.get("constraints") or []

    # Pattern A — healthy trade-off (CPA up but blended_roas improved vs prior window)
    if re.search(r"\b(cpa|costo)\b", brief_l) and ("alto" in brief_l or "alta" in brief_l):
        if len(runs) >= 2:
            last, prev = runs[0], runs[1]
            cpv_last = last.get("blended_cpv_observed")
            cpv_prev = prev.get("blended_cpv_observed")
            roas_last = last.get("blended_roas")
            roas_prev = prev.get("blended_roas")
            if (
                cpv_last is not None
                and cpv_prev is not None
                and cpv_last > cpv_prev
                and roas_last is not None
                and roas_prev is not None
                and roas_last > roas_prev
            ):
                return {
                    "diagnosis": (
                        "Trade-off sano: il CPA è salito ma il ROAS è migliorato. Non agire."
                    ),
                    "proposed_changes": [],
                    "expected_impact": None,
                }

    # Pattern B — low movement + CPA off target
    if len(runs) >= 3:
        movement_rates = []
        for r in runs[:3]:
            proposed = r.get("n_changes_proposed") or 0
            decisions_n = r.get("n_decisions") or 1
            movement_rates.append(proposed / max(decisions_n, 1))
        avg_movement = sum(movement_rates) / len(movement_rates)
        strategy = context.get("strategy") or {}
        primary_metric = strategy.get("primary_metric") or "cpv"
        target = strategy.get("primary_target")
        if target is None:
            target = settings.get("default_cpv_target", 0.5)
        last_cpv = runs[0].get("blended_cpv_observed")
        if primary_metric != "cpv":
            last_cpv = None
        if avg_movement < 0.05 and last_cpv is not None and last_cpv > target * 1.2:
            current = float(settings.get("max_step_per_run", 0.30))
            new_step = min(MAX_STEP_CAP, round(current + 0.05, 2))
            if new_step > current:
                return _settings_change(
                    settings,
                    "max_step_per_run",
                    current,
                    new_step,
                    "Movimento basso con CPA sopra target — aumento passo massimo",
                )

    # Pattern C — oscillation
    if len(decisions) >= 4:
        flips = 0
        prev_sign: int | None = None
        for d in decisions[:20]:
            delta = (d.get("new_modifier") or 0) - (d.get("previous_modifier") or 0)
            sign = 1 if delta > 0.01 else (-1 if delta < -0.01 else 0)
            if sign != 0:
                if prev_sign is not None and sign != prev_sign:
                    flips += 1
                prev_sign = sign
        if flips >= 2:
            current = float(settings.get("max_step_per_run", 0.30))
            new_step = max(0.10, round(current - 0.05, 2))
            if new_step < current:
                return _settings_change(
                    settings,
                    "max_step_per_run",
                    current,
                    new_step,
                    "Oscillazione termini — riduco passo massimo per stabilizzare",
                )

    # Pattern D — many constraint violations
    if constraints and decisions:
        violating = sum(
            1 for d in decisions
            if str(d.get("reason", "")).startswith("constraint")
        )
        if violating / max(len(decisions), 1) > 0.30:
            return {
                "diagnosis": (
                    "Oltre il 30% dei term è in violazione di hard constraint. "
                    "Valutare con l'umano se allargare le soglie."
                ),
                "proposed_changes": [],
                "expected_impact": {"confidence": "med"},
            }

    # Pattern E — downstream funnel drop
    if actions and len(runs) >= 2:
        funnel = sorted(
            [a for a in actions if a.get("funnel_position")],
            key=lambda a: a.get("funnel_position") or 0,
        )
        if len(funnel) >= 2:
            downstream = funnel[-1]
            # Heuristic: visits drop on blended when brief mentions funnel/downstream
            if re.search(r"\b(funnel|downstream|preliminare|conversione)\b", brief_l):
                vis_last = runs[0].get("blended_visits") or 0
                vis_prev = runs[1].get("blended_visits") or 1
                if vis_last < vis_prev * 0.70:
                    return {
                        "diagnosis": (
                            f"Drop downstream su action '{downstream.get('name')}': "
                            "non agire sul bidding, investigare tracking/landing."
                        ),
                        "proposed_changes": [],
                        "expected_impact": None,
                    }

    return None


def _settings_change(
    settings: dict,
    field: str,
    from_val: Any,
    to_val: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "diagnosis": reason,
        "proposed_changes": [{
            "entity": "settings",
            "entity_id": settings.get("id", ""),
            "field": field,
            "from": from_val,
            "to": to_val,
            "reason": reason,
        }],
        "expected_impact": {
            "primary_objective_delta_pct": -5.0,
            "volume_delta_pct": 3.0,
            "confidence": "med",
        },
    }
