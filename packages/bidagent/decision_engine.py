"""Decision engine: from observed performance to a plan of bid modifications.

Design choices:
- Pure function style. Input = current state + metrics. Output = Plan.
- No I/O here. Antenna/Buzz live in their own modules.
- Every decision carries its `reason` so the digest can narrate it.
- Velocity-capped: we never move a modifier more than `max_step_per_run`
  per pass. Slow and explainable beats fast and chaotic.
"""

from __future__ import annotations

import logging
from typing import Optional

from .models import (
    ActionMetric,
    ActionReason,
    ConstraintCheckResult,
    HardConstraintSpec,
    HygieneRules,
    LineItemChange,
    ModifierDecision,
    ModifierTerm,
    OptimizationProfile,
    OptimizerConfig,
    Plan,
    TermMetric,
)

log = logging.getLogger(__name__)


def _target_modifier_from_ratio(ratio: float, cfg: OptimizerConfig) -> float:
    """Map CPV ratio (observed / target) → desired modifier.

    Ratio < 1 means we're cheaper than target → bid up.
    Ratio > 1 means we're more expensive than target → bid down.

    This is intentionally a step function rather than a smooth curve, so
    the digest can say things like "this segment is 2x cheaper than target"
    in plain language."""

    if ratio < 0.50:
        return min(cfg.max_modifier, 1.50)
    if ratio < 0.80:
        return 1.25
    if ratio < (1.0 - cfg.tolerance_band):  # default 0.80, redundant but explicit
        return 1.10
    if ratio <= (1.0 + cfg.tolerance_band):  # on target band
        return 1.00
    if ratio < 1.50:
        return 0.80
    if ratio < 2.00:
        return 0.60
    if ratio < 3.00:
        return 0.40
    return 0.0  # 3x over target → zero out


def _smooth(current: float, target: float, max_step: float) -> tuple[float, bool]:
    """Cap the change between current and target. Returns (new, was_smoothed)."""
    delta = target - current
    if abs(delta) <= max_step:
        return target, False
    direction = 1 if delta > 0 else -1
    return current + direction * max_step, True


def decide_for_term(
    metric: TermMetric,
    current_modifier: float,
    cfg: OptimizerConfig,
    hygiene: HygieneRules,
    runs_since_zeroed: Optional[int] = None,
) -> ModifierDecision:
    """Produce one decision for one term.

    `runs_since_zeroed` lets the caller pass in how many runs ago this
    term was last set to 0. Used for the exploration revive policy."""

    term = ModifierTerm(
        targeting_module=metric.targeting_module,
        targeting_key=metric.targeting_key,
        value=metric.value,
        modifier=current_modifier,
        field_label=metric.field_label,
    )

    # --- hygiene gates (decided BEFORE looking at CPV) ---

    # Click-farm filter: catastrophically high CTR is almost always bots
    # on display/native. Zero immediately, no smoothing.
    if metric.ctr > hygiene.anomalous_ctr_threshold and metric.impressions >= 200:
        return ModifierDecision(
            term=ModifierTerm(**{**term.__dict__, "modifier": 0.0}),
            previous_modifier=current_modifier,
            new_modifier=0.0,
            reason=ActionReason.ANOMALOUS_CTR,
            observed_cpv=metric.cpv,
            observed_impressions=metric.impressions,
            observed_visits=metric.visits,
            note=f"CTR {metric.ctr:.2%} > soglia {hygiene.anomalous_ctr_threshold:.2%}",
        )

    # Viewability gate (only if tracked and required)
    if hygiene.require_viewability_tracking and metric.viewable_impressions > 0:
        if metric.viewability < hygiene.min_viewability:
            return ModifierDecision(
                term=ModifierTerm(**{**term.__dict__, "modifier": 0.0}),
                previous_modifier=current_modifier,
                new_modifier=0.0,
                reason=ActionReason.LOW_VIEWABILITY,
                observed_cpv=metric.cpv,
                observed_impressions=metric.impressions,
                observed_visits=metric.visits,
                note=f"Viewability {metric.viewability:.1%} < soglia {hygiene.min_viewability:.0%}",
            )

    # Volume gate: too few impressions → no action, hold previous modifier.
    if metric.impressions < hygiene.min_impressions_for_action:
        # Exploration revive: if the term has been zeroed for too long, give
        # it a small budget again to see if performance has changed.
        if (
            current_modifier == 0.0
            and runs_since_zeroed is not None
            and runs_since_zeroed >= cfg.exploration_revive_after_runs
        ):
            return ModifierDecision(
                term=ModifierTerm(
                    **{**term.__dict__, "modifier": cfg.exploration_revive_modifier}
                ),
                previous_modifier=current_modifier,
                new_modifier=cfg.exploration_revive_modifier,
                reason=ActionReason.EXPLORATION_REVIVE,
                observed_cpv=metric.cpv,
                observed_impressions=metric.impressions,
                observed_visits=metric.visits,
                note=f"Term zero da {runs_since_zeroed} run, rimetto in esplorazione",
            )
        return ModifierDecision(
            term=term,
            previous_modifier=current_modifier,
            new_modifier=current_modifier,
            reason=ActionReason.INSUFFICIENT_VOLUME,
            observed_cpv=metric.cpv,
            observed_impressions=metric.impressions,
            observed_visits=metric.visits,
            note=f"Solo {metric.impressions} impression, sotto soglia {hygiene.min_impressions_for_action}",
        )

    # Zero-visits: enough impressions but nobody is landing. Strong cut.
    if metric.visits == 0:
        proposed = 0.30  # almost off, but keep a sliver for re-observation
        new_value, smoothed = _smooth(current_modifier, proposed, cfg.max_step_per_run)
        return ModifierDecision(
            term=ModifierTerm(**{**term.__dict__, "modifier": new_value}),
            previous_modifier=current_modifier,
            new_modifier=new_value,
            reason=ActionReason.ZERO_VISITS,
            observed_cpv=metric.cpv,
            observed_impressions=metric.impressions,
            observed_visits=metric.visits,
            note=f"{metric.impressions} impression, 0 visite — taglio profondo",
        )

    # --- main decision: CPV ratio ---
    ratio = metric.cpv / cfg.cpv_target if cfg.cpv_target > 0 else 1.0
    target_modifier = _target_modifier_from_ratio(ratio, cfg)

    # Enforce min active modifier (don't kill unless really bad)
    if 0 < target_modifier < cfg.min_modifier_active:
        target_modifier = cfg.min_modifier_active

    # Smooth: cap delta per run
    new_value, was_smoothed = _smooth(
        current_modifier, target_modifier, cfg.max_step_per_run
    )

    # Determine reason
    if ratio < (1.0 - cfg.tolerance_band):
        reason = ActionReason.UNDER_TARGET
    elif ratio > (1.0 + cfg.tolerance_band):
        reason = ActionReason.OVER_TARGET
    else:
        reason = ActionReason.ON_TARGET

    if was_smoothed and reason != ActionReason.ON_TARGET:
        # Reason stays semantic (under/over), but we annotate it
        note = (
            f"CPV {metric.cpv:.2f}€ vs target {cfg.cpv_target:.2f}€ "
            f"(ratio {ratio:.2f}), passo limitato a ±{cfg.max_step_per_run}"
        )
    else:
        note = (
            f"CPV {metric.cpv:.2f}€ vs target {cfg.cpv_target:.2f}€ "
            f"(ratio {ratio:.2f})"
        )

    return ModifierDecision(
        term=ModifierTerm(**{**term.__dict__, "modifier": new_value}),
        previous_modifier=current_modifier,
        new_modifier=new_value,
        reason=reason,
        observed_cpv=metric.cpv,
        observed_impressions=metric.impressions,
        observed_visits=metric.visits,
        note=note,
    )


def decide_blended_max_bid(
    blended_cpv: float,
    current_max_bid: float,
    cfg: OptimizerConfig,
    line_item_id: int,
) -> Optional[LineItemChange]:
    """Adjust the Line Item-level max_bid based on blended CPV.

    Conservative: ±10% per run, hard floor and ceiling. We move max_bid
    only when the blended is meaningfully off target (>20% band)."""

    if cfg.cpv_target <= 0:
        return None

    ratio = blended_cpv / cfg.cpv_target
    if abs(ratio - 1.0) <= cfg.tolerance_band:
        return None  # blended is on target, leave max_bid alone

    if ratio > 1.0:
        # Spending too much per visit → tighten max_bid
        new_max_bid = current_max_bid * (1.0 - cfg.blended_max_bid_step)
        direction = "ridotto"
    else:
        # Cheap visits → can afford a higher ceiling
        new_max_bid = current_max_bid * (1.0 + cfg.blended_max_bid_step)
        direction = "alzato"

    new_max_bid = max(cfg.blended_max_bid_floor,
                      min(cfg.blended_max_bid_ceiling, new_max_bid))

    if abs(new_max_bid - current_max_bid) < 0.01:
        return None

    return LineItemChange(
        line_item_id=line_item_id,
        field="max_bid",
        previous_value=round(current_max_bid, 2),
        new_value=round(new_max_bid, 2),
        reason=(
            f"Blended CPV {blended_cpv:.2f}€ vs target {cfg.cpv_target:.2f}€ "
            f"(ratio {ratio:.2f}) → max_bid {direction} a {new_max_bid:.2f}€"
        ),
    )


def build_plan(
    line_item_id: int,
    line_item_name: str,
    week_label: str,
    metrics: list[TermMetric],
    current_modifiers: dict[tuple[str, str, str], float],
    runs_since_zeroed: dict[tuple[str, str, str], int],
    current_max_bid: float,
    cfg: OptimizerConfig,
    hygiene: HygieneRules,
) -> Plan:
    """End-to-end: from raw metrics to a full Plan for one Line Item."""

    decisions: list[ModifierDecision] = []
    for m in metrics:
        key = (m.targeting_module, m.targeting_key, str(m.value))
        prev = current_modifiers.get(key, 1.0)
        runs_zero = runs_since_zeroed.get(key)
        d = decide_for_term(m, prev, cfg, hygiene, runs_since_zeroed=runs_zero)
        decisions.append(d)

    # Blended stats
    total_spend = sum(m.spend for m in metrics)
    total_visits = sum(m.visits for m in metrics)
    blended_cpv = (total_spend / total_visits) if total_visits else float("inf")

    plan = Plan(
        line_item_id=line_item_id,
        line_item_name=line_item_name,
        cpv_target=cfg.cpv_target,
        blended_cpv_observed=blended_cpv,
        blended_visits=total_visits,
        blended_spend=total_spend,
        decisions=decisions,
        week_label=week_label,
    )

    # Line Item level change (max_bid)
    if blended_cpv != float("inf"):
        change = decide_blended_max_bid(blended_cpv, current_max_bid, cfg, line_item_id)
        if change:
            plan.line_item_changes.append(change)

    return plan


def _term_metric_value(metric: TermMetric, name: str) -> float:
    if name == "cpc":
        return metric.spend / metric.clicks if metric.clicks else float("inf")
    if name == "cpm":
        return (metric.spend / metric.impressions * 1000) if metric.impressions else float("inf")
    if name == "cpcv":
        return metric.spend / metric.viewable_impressions if metric.viewable_impressions else float("inf")
    if name == "vtr":
        return metric.visit_rate
    if name == "viewability":
        return metric.viewability
    if name == "fraud_rate":
        return metric.ctr  # placeholder until dedicated signal exists
    return float("nan")


def _constraint_violated(observed: float, operator: str, threshold: float) -> bool:
    if observed != observed:  # NaN
        return False
    if operator == "lte":
        return observed > threshold
    return observed < threshold


def _check_hard_constraints(
    metric: TermMetric,
    constraints: list[HardConstraintSpec],
) -> ConstraintCheckResult | None:
    for c in constraints:
        if c.status != "active":
            continue
        observed = _term_metric_value(metric, c.metric)
        if _constraint_violated(observed, c.operator, c.value):
            return ConstraintCheckResult(
                violated=True,
                metric=c.metric,
                operator=c.operator,
                observed=observed,
                threshold=c.value,
                policy=c.violation_policy,
            )
    return None


def _blended_cpa(metric: TermMetric, actions: list[ActionMetric]) -> float:
    weighted = sum(a.weight * a.count for a in actions)
    if weighted <= 0:
        return float("inf")
    return metric.spend / weighted


def _observed_roas(metric: TermMetric, actions: list[ActionMetric]) -> float:
    if metric.spend <= 0:
        return 0.0
    value = sum(a.value_eur * a.count for a in actions)
    return value / metric.spend


def _primary_ratio(
    metric: TermMetric,
    strategy: OptimizationProfile,
    actions: list[ActionMetric],
) -> float:
    target = strategy.primary_objective_target
    if target <= 0:
        return 1.0

    if strategy.profile in ("minimize_cpv",) or strategy.primary_objective_metric == "cpv":
        observed = metric.cpv
    elif strategy.profile == "minimize_blended_cpa" or strategy.primary_objective_metric == "blended_cpa":
        observed = _blended_cpa(metric, actions)
    elif strategy.profile == "maximize_value_at_target_roas" or strategy.primary_objective_metric == "roas":
        observed = _observed_roas(metric, actions)
        return target / observed if observed > 0 else float("inf")
    else:
        observed = metric.cpv

    if observed == float("inf"):
        return float("inf")
    return observed / target


def _apply_constraint_policy(
    *,
    current_modifier: float,
    check: ConstraintCheckResult,
    cfg: OptimizerConfig,
    term: ModifierTerm,
    metric: TermMetric,
) -> ModifierDecision:
    policy = check.policy
    if policy == "freeze":
        new_modifier = current_modifier
    elif policy == "throttle":
        proposed = max(cfg.min_modifier_active, current_modifier * 0.7)
        new_modifier, _ = _smooth(current_modifier, proposed, cfg.max_step_per_run)
    elif policy == "kill":
        new_modifier = 0.0
    else:  # alert
        new_modifier = current_modifier

    return ModifierDecision(
        term=ModifierTerm(**{**term.__dict__, "modifier": new_modifier}),
        previous_modifier=current_modifier,
        new_modifier=new_modifier,
        reason=ActionReason.CONSTRAINT_VIOLATED,
        observed_cpv=metric.cpv,
        observed_impressions=metric.impressions,
        observed_visits=metric.visits,
        note=(
            f"constraint_violated_{check.metric}: "
            f"observed {check.observed:.4f} {check.operator} {check.threshold} ({policy})"
        ),
    )


def decide_multi_objective_for_term(
    metric: TermMetric,
    current_modifier: float,
    cfg: OptimizerConfig,
    hygiene: HygieneRules,
    strategy: OptimizationProfile,
    constraints: list[HardConstraintSpec],
    actions: list[ActionMetric],
    runs_since_zeroed: Optional[int] = None,
) -> ModifierDecision:
    """Multi-objective path: hygiene → hard constraints → primary objective."""
    if strategy.profile == "minimize_cpv" and not constraints:
        return decide_for_term(metric, current_modifier, cfg, hygiene, runs_since_zeroed)

    term = ModifierTerm(
        targeting_module=metric.targeting_module,
        targeting_key=metric.targeting_key,
        value=metric.value,
        modifier=current_modifier,
        field_label=metric.field_label,
    )

    hygiene_decision = decide_for_term(
        metric, current_modifier, cfg, hygiene, runs_since_zeroed,
    )
    if hygiene_decision.reason in (
        ActionReason.ANOMALOUS_CTR,
        ActionReason.LOW_VIEWABILITY,
        ActionReason.INSUFFICIENT_VOLUME,
        ActionReason.EXPLORATION_REVIVE,
    ):
        return hygiene_decision

    check = _check_hard_constraints(metric, constraints)
    if check is not None:
        return _apply_constraint_policy(
            current_modifier=current_modifier,
            check=check,
            cfg=cfg,
            term=term,
            metric=metric,
        )

    ratio = _primary_ratio(metric, strategy, actions)
    if ratio == float("inf"):
        ratio = 3.0

    target_modifier = _target_modifier_from_ratio(ratio, cfg)
    if 0 < target_modifier < cfg.min_modifier_active:
        target_modifier = cfg.min_modifier_active

    new_value, was_smoothed = _smooth(
        current_modifier, target_modifier, cfg.max_step_per_run,
    )

    if ratio < (1.0 - strategy.tolerance_band):
        reason = ActionReason.UNDER_TARGET
    elif ratio > (1.0 + strategy.tolerance_band):
        reason = ActionReason.OVER_TARGET
    else:
        reason = ActionReason.ON_TARGET

    note = (
        f"{strategy.profile} ratio {ratio:.2f} vs target {strategy.primary_objective_target}"
    )
    if was_smoothed and reason != ActionReason.ON_TARGET:
        note += f", passo limitato a ±{cfg.max_step_per_run}"

    return ModifierDecision(
        term=ModifierTerm(**{**term.__dict__, "modifier": new_value}),
        previous_modifier=current_modifier,
        new_modifier=new_value,
        reason=reason,
        observed_cpv=metric.cpv,
        observed_impressions=metric.impressions,
        observed_visits=metric.visits,
        note=note,
    )


def decide_multi_objective(
    line_item_id: int,
    line_item_name: str,
    week_label: str,
    metrics: list[TermMetric],
    current_modifiers: dict[tuple[str, str, str], float],
    runs_since_zeroed: dict[tuple[str, str, str], int],
    current_max_bid: float,
    cfg: OptimizerConfig,
    hygiene: HygieneRules,
    strategy: OptimizationProfile | None = None,
    constraints: list[HardConstraintSpec] | None = None,
    actions_by_term: dict[tuple[str, str, str], list[ActionMetric]] | None = None,
) -> Plan:
    """Multi-objective plan builder. Default path matches legacy `build_plan`."""
    strategy = strategy or OptimizationProfile(
        profile="minimize_cpv",
        primary_objective_target=cfg.cpv_target,
        tolerance_band=cfg.tolerance_band,
    )
    constraints = constraints or []
    actions_by_term = actions_by_term or {}

    if strategy.profile == "minimize_cpv" and not constraints:
        return build_plan(
            line_item_id,
            line_item_name,
            week_label,
            metrics,
            current_modifiers,
            runs_since_zeroed,
            current_max_bid,
            cfg,
            hygiene,
        )

    decisions: list[ModifierDecision] = []
    for m in metrics:
        key = (m.targeting_module, m.targeting_key, str(m.value))
        prev = current_modifiers.get(key, 1.0)
        runs_zero = runs_since_zeroed.get(key)
        term_actions = actions_by_term.get(key, [])
        d = decide_multi_objective_for_term(
            m,
            prev,
            cfg,
            hygiene,
            strategy,
            constraints,
            term_actions,
            runs_since_zeroed=runs_zero,
        )
        decisions.append(d)

    total_spend = sum(m.spend for m in metrics)
    total_visits = sum(m.visits for m in metrics)
    blended_cpv = (total_spend / total_visits) if total_visits else float("inf")

    plan = Plan(
        line_item_id=line_item_id,
        line_item_name=line_item_name,
        cpv_target=cfg.cpv_target,
        blended_cpv_observed=blended_cpv,
        blended_visits=total_visits,
        blended_spend=total_spend,
        decisions=decisions,
        week_label=week_label,
    )

    if blended_cpv != float("inf"):
        change = decide_blended_max_bid(blended_cpv, current_max_bid, cfg, line_item_id)
        if change:
            plan.line_item_changes.append(change)

    return plan
