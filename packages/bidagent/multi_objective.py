"""Metric-agnostic blended score engine (epsilon-constraint style)."""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from .decision_engine import (
    _smooth,
    _target_modifier_from_ratio,
    decide_for_term,
    decide_blended_max_bid,
)
from .models import (
    ActionMetric,
    ActionReason,
    ConstraintCheckResult,
    HardConstraintSpec,
    HygieneRules,
    ModifierDecision,
    ModifierTerm,
    OptimizerConfig,
    Plan,
    TermMetric,
)

log = logging.getLogger(__name__)

MetricDirection = Literal["minimize", "maximize"]
ConstraintPolicy = Literal["freeze", "throttle", "kill", "alert"]


@dataclass
class MetricSpec:
    name: str
    target: float
    weight_pct: float
    direction: MetricDirection


@dataclass
class ActionSpec:
    action_id: str
    weight: float
    value_eur: float


@dataclass
class ConstraintSpec:
    metric: str
    operator: Literal["gte", "lte"]
    value: float
    policy: ConstraintPolicy
    status: str = "active"


@dataclass
class MetricBaseline:
    """Population baseline for z-score normalization (e.g. last 14d window)."""

    mean: float
    std: float


@dataclass
class StrategySpec:
    mode: Literal["single", "blended_2", "blended_3"]
    metrics: list[MetricSpec]
    tolerance_band: float
    constraints: list[ConstraintSpec] = field(default_factory=list)
    actions: list[ActionSpec] = field(default_factory=list)
    metric_baselines: dict[str, MetricBaseline] = field(default_factory=dict)


@dataclass
class ConstraintViolation:
    metric: str
    operator: str
    observed: float
    threshold: float
    policy: ConstraintPolicy


MINIMIZE = frozenset({"cpv", "cpc", "cpcv", "cpm", "cpa"})
MAXIMIZE = frozenset({"roas", "custom_action"})


def validate_strategy_weights(strategy: StrategySpec) -> None:
    total = sum(m.weight_pct for m in strategy.metrics)
    if abs(total - 100) > 0.01:
        raise ValueError(f"metric weights must sum to 100, got {total}")


def metric_direction(name: str) -> MetricDirection:
    if name in MINIMIZE:
        return "minimize"
    if name in MAXIMIZE:
        return "maximize"
    raise ValueError(f"unknown metric: {name}")


def build_strategy_spec(
    *,
    mode: str,
    primary_metric: str,
    primary_target: float,
    primary_weight: float,
    secondary_metric: str | None = None,
    secondary_target: float | None = None,
    secondary_weight: float | None = None,
    tertiary_metric: str | None = None,
    tertiary_target: float | None = None,
    tertiary_weight: float | None = None,
    tolerance_band: float = 0.20,
    constraints: list[HardConstraintSpec] | None = None,
    actions: list[ActionMetric] | None = None,
) -> StrategySpec:
    metrics: list[MetricSpec] = [
        MetricSpec(
            primary_metric,
            primary_target,
            primary_weight,
            metric_direction(primary_metric),
        ),
    ]
    if mode in ("blended_2", "blended_3") and secondary_metric and secondary_target is not None:
        metrics.append(
            MetricSpec(
                secondary_metric,
                secondary_target,
                float(secondary_weight or 0),
                metric_direction(secondary_metric),
            ),
        )
    if mode == "blended_3" and tertiary_metric and tertiary_target is not None:
        metrics.append(
            MetricSpec(
                tertiary_metric,
                tertiary_target,
                float(tertiary_weight or 0),
                metric_direction(tertiary_metric),
            ),
        )
    spec = StrategySpec(
        mode=mode,  # type: ignore[arg-type]
        metrics=metrics,
        tolerance_band=tolerance_band,
        constraints=[
            ConstraintSpec(
                metric=c.metric,
                operator=c.operator,  # type: ignore[arg-type]
                value=c.value,
                policy=c.violation_policy,  # type: ignore[arg-type]
                status=c.status,
            )
            for c in (constraints or [])
        ],
        actions=[
            ActionSpec(a.action_id, a.weight, a.value_eur)
            for a in (actions or [])
        ],
    )
    validate_strategy_weights(spec)
    return spec


def _term_observed_metric(
    metric: TermMetric,
    name: str,
    actions: list[ActionSpec],
) -> float:
    if name == "cpv":
        return metric.cpv
    if name == "cpc":
        return metric.spend / metric.clicks if metric.clicks else float("inf")
    if name == "cpm":
        return (metric.spend / metric.impressions * 1000) if metric.impressions else float("inf")
    if name == "cpcv":
        return (
            metric.spend / metric.viewable_impressions
            if metric.viewable_impressions
            else float("inf")
        )
    if name == "cpa":
        weighted = sum(a.weight for a in actions) or 1.0
        return metric.spend / weighted
    if name == "roas":
        if metric.spend <= 0:
            return 0.0
        return sum(a.value_eur for a in actions) / metric.spend
    if name == "custom_action":
        if metric.spend <= 0:
            return 0.0
        return sum(a.value_eur for a in actions) / metric.spend
    if name == "viewability":
        return metric.viewability
    if name == "vtr":
        return metric.visit_rate
    if name == "fraud_rate":
        return metric.ctr
    return float("nan")


def build_metric_baselines(metrics: list[TermMetric]) -> dict[str, MetricBaseline]:
    """Cross-term baselines from the observation window (proxy for 14d rolling stats)."""
    series: dict[str, list[float]] = defaultdict(list)
    for m in metrics:
        if m.impressions < 100:
            continue
        if m.visits > 0 and m.cpv != float("inf"):
            series["cpv"].append(m.cpv)
        if m.clicks > 0:
            series["cpc"].append(m.spend / m.clicks)
        if m.impressions > 0:
            series["cpm"].append(m.spend / m.impressions * 1000)
            series["viewability"].append(m.viewability)
        if m.clicks > 0:
            series["cpa"].append(m.spend / max(m.visits, 1))
    out: dict[str, MetricBaseline] = {}
    for name, vals in series.items():
        if len(vals) < 2:
            continue
        mean = statistics.fmean(vals)
        std = statistics.pstdev(vals)
        out[name] = MetricBaseline(mean=mean, std=max(std, 1e-9))
    return out


def _ratio_score(observed: float, target: float, direction: MetricDirection) -> float:
    if observed != observed or target <= 0:
        return 1.0
    if direction == "minimize":
        raw = target / observed if observed > 0 else 2.0
    else:
        raw = observed / target
    return max(0.0, min(2.0, raw))


def _normalize_score(
    observed: float,
    target: float,
    direction: MetricDirection,
    baseline: MetricBaseline | None,
) -> float:
    ratio = _ratio_score(observed, target, direction)
    if baseline is None or baseline.std < 1e-9:
        return ratio
    z = (observed - baseline.mean) / baseline.std
    if direction == "minimize":
        z_score = 1.0 - 0.35 * z
    else:
        z_score = 1.0 + 0.35 * z
    z_score = max(0.0, min(2.0, z_score))
    return max(0.0, min(2.0, 0.55 * z_score + 0.45 * ratio))


def compute_blended_score(
    observed: TermMetric,
    strategy: StrategySpec,
    *,
    term_actions: list[ActionSpec] | None = None,
) -> float:
    """Blended normalized score; 1.0 = on-target."""
    validate_strategy_weights(strategy)
    actions = term_actions or strategy.actions
    total = 0.0
    for m in strategy.metrics:
        obs = _term_observed_metric(observed, m.name, actions)
        baseline = strategy.metric_baselines.get(m.name)
        part = _normalize_score(obs, m.target, m.direction, baseline)
        total += (m.weight_pct / 100.0) * part
    return total


def check_constraints(
    observed: TermMetric,
    constraints: list[ConstraintSpec],
) -> ConstraintViolation | None:
    for c in constraints:
        if c.status != "active":
            continue
        val = _term_observed_metric(observed, c.metric, [])
        if val != val:
            continue
        violated = (
            val > c.value if c.operator == "lte" else val < c.value
        )
        if violated:
            return ConstraintViolation(
                metric=c.metric,
                operator=c.operator,
                observed=val,
                threshold=c.value,
                policy=c.policy,
            )
    return None


def _apply_violation(
    *,
    current_modifier: float,
    violation: ConstraintViolation,
    cfg: OptimizerConfig,
    term: ModifierTerm,
    metric: TermMetric,
) -> ModifierDecision:
    policy = violation.policy
    if policy == "freeze":
        new_modifier = current_modifier
        reason = ActionReason.CONSTRAINT_VIOLATED
    elif policy == "throttle":
        proposed = max(cfg.min_modifier_active, current_modifier * 0.7)
        new_modifier, _ = _smooth(current_modifier, proposed, cfg.max_step_per_run)
        reason = ActionReason.CONSTRAINT_VIOLATED
    elif policy == "kill":
        new_modifier = 0.0
        reason = ActionReason.CONSTRAINT_VIOLATED
    else:
        log.warning(
            "constraint alert %s: observed=%.4f %s %.4f",
            violation.metric,
            violation.observed,
            violation.operator,
            violation.threshold,
        )
        new_modifier = current_modifier
        reason = ActionReason.ON_TARGET

    return ModifierDecision(
        term=ModifierTerm(**{**term.__dict__, "modifier": new_modifier}),
        previous_modifier=current_modifier,
        new_modifier=new_modifier,
        reason=reason,
        observed_cpv=metric.cpv,
        observed_impressions=metric.impressions,
        observed_visits=metric.visits,
        note=f"constraint_{policy}_{violation.metric}",
    )


def decide_term_metric_agnostic(
    metric: TermMetric,
    current_modifier: float,
    cfg: OptimizerConfig,
    hygiene: HygieneRules,
    strategy: StrategySpec,
    runs_since_zeroed: int | None = None,
    term_actions: list[ActionSpec] | None = None,
) -> ModifierDecision:
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
        ActionReason.ZERO_VISITS,
    ):
        return hygiene_decision

    violation = check_constraints(metric, strategy.constraints)
    if violation is not None and violation.policy != "alert":
        return _apply_violation(
            current_modifier=current_modifier,
            violation=violation,
            cfg=cfg,
            term=term,
            metric=metric,
        )

    score = compute_blended_score(metric, strategy, term_actions=term_actions)
    ratio = 1.0 / score if score > 0 else 3.0

    target_modifier = _target_modifier_from_ratio(ratio, cfg)
    if 0 < target_modifier < cfg.min_modifier_active:
        target_modifier = cfg.min_modifier_active

    new_value, was_smoothed = _smooth(
        current_modifier, target_modifier, cfg.max_step_per_run,
    )

    band = strategy.tolerance_band
    if score > 1.0 + band:
        reason = ActionReason.UNDER_TARGET
    elif score < 1.0 - band:
        reason = ActionReason.OVER_TARGET
    else:
        reason = ActionReason.ON_TARGET

    note = f"blended_score={score:.3f} mode={strategy.mode}"
    if was_smoothed and reason != ActionReason.ON_TARGET:
        note += f", passo ±{cfg.max_step_per_run}"

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


def build_plan_metric_agnostic(
    line_item_id: int,
    line_item_name: str,
    week_label: str,
    metrics: list[TermMetric],
    current_modifiers: dict[tuple[str, str, str], float],
    runs_since_zeroed: dict[tuple[str, str, str], int],
    current_max_bid: float,
    cfg: OptimizerConfig,
    hygiene: HygieneRules,
    strategy: StrategySpec,
    actions_by_term: dict[tuple[str, str, str], list[ActionMetric]] | None = None,
) -> Plan:
    actions_by_term = actions_by_term or {}
    decisions: list[ModifierDecision] = []
    for m in metrics:
        key = (m.targeting_module, m.targeting_key, str(m.value))
        prev = current_modifiers.get(key, 1.0)
        term_action_metrics = actions_by_term.get(key, [])
        term_actions = [
            ActionSpec(a.action_id, a.weight, a.value_eur) for a in term_action_metrics
        ]
        d = decide_term_metric_agnostic(
            m,
            prev,
            cfg,
            hygiene,
            strategy,
            runs_since_zeroed=runs_since_zeroed.get(key),
            term_actions=term_actions,
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
