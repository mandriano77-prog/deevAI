"""Bridge tenant DB config → bidagent plan builder (legacy CPV or metric-agnostic)."""

from __future__ import annotations

from bidagent.decision_engine import build_plan
from bidagent.models import ActionMetric, HardConstraintSpec, HygieneRules, OptimizerConfig, Plan, TermMetric
from bidagent.multi_objective import (
    build_metric_baselines,
    build_plan_metric_agnostic,
    build_strategy_spec,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Action, LineItem, OptimizationStrategy, Setting
from .actions import get_action_funnel
from .optimization import list_constraints, resolve_effective_strategy


def compute_blended_roas(
    actions: list[Action],
    blended_spend: float | None,
) -> float | None:
    if not blended_spend or blended_spend <= 0 or not actions:
        return None
    total_value = sum(float(a.value_eur) for a in actions)
    return round(total_value / blended_spend, 4)


def optimizer_config_from_models(
    line_item: LineItem,
    setting: Setting | None,
) -> tuple[OptimizerConfig, HygieneRules]:
    def _f(val: float | int | None, default: float) -> float:
        return float(val) if val is not None else default

    def _i(val: int | None, default: int) -> int:
        return int(val) if val is not None else default

    cfg = OptimizerConfig(
        cpv_target=float(line_item.cpv_target),
        tolerance_band=_f(setting.tolerance_band if setting else None, 0.20),
        max_step_per_run=_f(setting.max_step_per_run if setting else None, 0.30),
        max_modifier=_f(setting.max_modifier if setting else None, 2.50),
        min_modifier_active=_f(setting.min_modifier_active if setting else None, 0.30),
        exploration_revive_after_runs=_i(
            setting.exploration_revive_after_runs if setting else None, 4,
        ),
        exploration_revive_modifier=_f(
            setting.exploration_revive_modifier if setting else None, 0.50,
        ),
    )
    hygiene = HygieneRules(
        min_impressions_for_action=_i(
            setting.min_impressions_for_action if setting else None, 500,
        ),
        min_visits_for_strong_action=_i(
            setting.min_visits_for_strong_action if setting else None, 10,
        ),
        anomalous_ctr_threshold=_f(
            setting.anomalous_ctr_threshold if setting else None, 0.04,
        ),
        min_viewability=_f(setting.min_viewability if setting else None, 0.40),
    )
    return cfg, hygiene


def _strategy_to_spec(
    strategy: OptimizationStrategy,
    constraints: list[HardConstraintSpec],
    funnel_actions: list[Action],
) -> object:
    action_metrics = [
        ActionMetric(action_id=a.id, weight=float(a.weight), value_eur=float(a.value_eur), count=1)
        for a in funnel_actions
    ]
    return build_strategy_spec(
        mode=strategy.mode,
        primary_metric=strategy.primary_metric,
        primary_target=float(strategy.primary_target),
        primary_weight=float(strategy.primary_weight),
        secondary_metric=strategy.secondary_metric,
        secondary_target=float(strategy.secondary_target) if strategy.secondary_target else None,
        secondary_weight=float(strategy.secondary_weight) if strategy.secondary_weight else None,
        tertiary_metric=strategy.tertiary_metric,
        tertiary_target=float(strategy.tertiary_target) if strategy.tertiary_target else None,
        tertiary_weight=float(strategy.tertiary_weight) if strategy.tertiary_weight else None,
        tolerance_band=float(strategy.tolerance_band),
        constraints=constraints,
        actions=action_metrics,
    )


async def build_line_item_plan(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item: LineItem,
    setting: Setting | None,
    metrics: list[TermMetric],
    current_modifiers: dict[tuple[str, str, str], float],
    runs_since_zeroed: dict[tuple[str, str, str], int],
    current_max_bid: float,
    week_label: str,
) -> Plan:
    cfg, hygiene = optimizer_config_from_models(line_item, setting)
    li_key = (
        int(line_item.amazon_line_item_id)
        if line_item.amazon_line_item_id.isdigit()
        else 0
    )

    strategy = await resolve_effective_strategy(
        db, tenant_id=tenant_id, line_item_id=line_item.id,
    )

    if strategy is None or strategy.status != "active":
        return build_plan(
            li_key,
            line_item.name,
            week_label,
            metrics,
            current_modifiers,
            runs_since_zeroed,
            current_max_bid,
            cfg,
            hygiene,
        )

    constraint_rows = await list_constraints(
        db, tenant_id=tenant_id, strategy_id=strategy.id,
    )
    constraint_specs = [
        HardConstraintSpec(
            metric=c.metric,
            operator=c.operator,
            value=float(c.value),
            violation_policy=c.violation_policy,
            status=c.status,
        )
        for c in constraint_rows
    ]

    funnel = await get_action_funnel(db, tenant_id=tenant_id)
    spec = _strategy_to_spec(strategy, constraint_specs, funnel)
    spec.metric_baselines = build_metric_baselines(metrics)

    use_legacy = (
        strategy.mode == "single"
        and strategy.primary_metric == "cpv"
        and not constraint_specs
    )

    if use_legacy:
        return build_plan(
            li_key,
            line_item.name,
            week_label,
            metrics,
            current_modifiers,
            runs_since_zeroed,
            current_max_bid,
            cfg,
            hygiene,
        )

    per_term_actions: list[ActionMetric] = [
        ActionMetric(action_id=a.id, weight=float(a.weight), value_eur=float(a.value_eur), count=1)
        for a in funnel
    ]
    actions_by_term: dict[tuple[str, str, str], list[ActionMetric]] = {}
    if metrics and per_term_actions:
        for m in metrics:
            key = (m.targeting_module, m.targeting_key, str(m.value))
            actions_by_term[key] = per_term_actions

    return build_plan_metric_agnostic(
        li_key,
        line_item.name,
        week_label,
        metrics,
        current_modifiers,
        runs_since_zeroed,
        current_max_bid,
        cfg,
        hygiene,
        spec,
        actions_by_term=actions_by_term,
    )
