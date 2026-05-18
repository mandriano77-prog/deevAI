"""Metric-agnostic multi-objective engine — 8 acceptance tests."""

from __future__ import annotations

import logging

import pytest

from bidagent.decision_engine import build_plan, decide_multi_objective
from bidagent.models import (
    ActionMetric,
    ActionReason,
    HardConstraintSpec,
    HygieneRules,
    OptimizationProfile,
    OptimizerConfig,
    TermMetric,
)
from bidagent.multi_objective import (
    ActionSpec,
    ConstraintSpec,
    MetricSpec,
    StrategySpec,
    build_metric_baselines,
    build_plan_metric_agnostic,
    build_strategy_spec,
    check_constraints,
    compute_blended_score,
    decide_term_metric_agnostic,
    validate_strategy_weights,
)


def _metric(**kwargs) -> TermMetric:
    defaults = dict(
        targeting_module="platform",
        targeting_key="browser",
        value="safari",
        field_label="Safari",
        impressions=5000,
        clicks=50,
        visits=20,
        spend=8.0,
        viewable_impressions=3250,
    )
    defaults.update(kwargs)
    return TermMetric(**defaults)


def test_legacy_cpv_path_unchanged() -> None:
    cfg = OptimizerConfig(cpv_target=0.60, tolerance_band=0.20, max_step_per_run=0.30)
    hygiene = HygieneRules(min_impressions_for_action=500)
    metrics = [_metric()]
    mods = {("platform", "browser", "safari"): 1.0}

    legacy = build_plan(1, "LI", "W01", metrics, mods, {}, 5.0, cfg, hygiene)
    multi = decide_multi_objective(1, "LI", "W01", metrics, mods, {}, 5.0, cfg, hygiene)
    for a, b in zip(legacy.decisions, multi.decisions, strict=True):
        assert a.new_modifier == b.new_modifier
        assert a.reason == b.reason


def test_blended_70_cpa_30_cpc_score() -> None:
    m = _metric(spend=80.0, clicks=100)
    spec = build_strategy_spec(
        mode="blended_2",
        primary_metric="cpa",
        primary_target=4.0,
        primary_weight=70,
        secondary_metric="cpc",
        secondary_target=0.10,
        secondary_weight=30,
    )
    actions = [ActionSpec("a1", 1.0, 1.0)]
    score = compute_blended_score(m, spec, term_actions=actions)
    assert 0.0 < score <= 2.0


def test_maximize_roas_direction() -> None:
    m = _metric(spend=10.0)
    spec = StrategySpec(
        mode="single",
        metrics=[MetricSpec("roas", 2.0, 100.0, "maximize")],
        tolerance_band=0.2,
        actions=[ActionSpec("a1", 1.0, 25.0)],
    )
    score_on = compute_blended_score(m, spec)
    assert abs(score_on - 1.25) < 0.01


def test_constraint_freeze() -> None:
    m = _metric(clicks=200, spend=40.0)
    cfg = OptimizerConfig(cpv_target=0.6, max_step_per_run=0.3)
    hygiene = HygieneRules(min_impressions_for_action=500, require_viewability_tracking=False)
    spec = build_strategy_spec(
        mode="single",
        primary_metric="cpv",
        primary_target=0.6,
        primary_weight=100,
        constraints=[HardConstraintSpec("cpc", "lte", 0.15, "freeze")],
    )
    d = decide_term_metric_agnostic(m, 1.2, cfg, hygiene, spec)
    assert d.reason == ActionReason.CONSTRAINT_VIOLATED
    assert d.new_modifier == 1.2


def test_constraint_throttle_respects_min_modifier() -> None:
    m = _metric(clicks=200, spend=40.0)
    cfg = OptimizerConfig(cpv_target=0.6, max_step_per_run=0.3, min_modifier_active=0.35)
    hygiene = HygieneRules(min_impressions_for_action=500, require_viewability_tracking=False)
    spec = build_strategy_spec(
        mode="single",
        primary_metric="cpv",
        primary_target=0.6,
        primary_weight=100,
        constraints=[HardConstraintSpec("cpc", "lte", 0.15, "throttle")],
    )
    d = decide_term_metric_agnostic(m, 1.0, cfg, hygiene, spec)
    assert d.new_modifier >= cfg.min_modifier_active


def test_constraint_kill() -> None:
    m = _metric(viewable_impressions=2400, impressions=8000)
    cfg = OptimizerConfig(cpv_target=0.6, max_step_per_run=0.3)
    hygiene = HygieneRules(
        min_impressions_for_action=500,
        min_viewability=0.1,
        require_viewability_tracking=False,
    )
    spec = build_strategy_spec(
        mode="single",
        primary_metric="cpv",
        primary_target=0.6,
        primary_weight=100,
        constraints=[
            HardConstraintSpec("viewability", "gte", 0.50, "kill"),
        ],
    )
    d = decide_term_metric_agnostic(m, 1.0, cfg, hygiene, spec)
    assert d.new_modifier == 0.0


def test_constraint_alert_continues(caplog: pytest.LogCaptureFixture) -> None:
    m = _metric(clicks=200, spend=40.0)
    cfg = OptimizerConfig(cpv_target=0.6, max_step_per_run=0.3, tolerance_band=0.2)
    hygiene = HygieneRules(min_impressions_for_action=500, require_viewability_tracking=False)
    spec = build_strategy_spec(
        mode="single",
        primary_metric="cpv",
        primary_target=0.6,
        primary_weight=100,
        constraints=[HardConstraintSpec("cpc", "lte", 0.15, "alert")],
    )
    with caplog.at_level(logging.WARNING):
        d = decide_term_metric_agnostic(m, 1.0, cfg, hygiene, spec)
    assert "constraint alert" in caplog.text.lower() or d.reason != ActionReason.CONSTRAINT_VIOLATED


def test_zscore_baseline_differs_from_ratio_only() -> None:
    metrics = [
        _metric(spend=8.0, visits=20),
        _metric(spend=16.0, visits=20, value="chrome"),
        _metric(spend=24.0, visits=20, value="firefox"),
    ]
    baselines = build_metric_baselines(metrics)
    spec = build_strategy_spec(
        mode="single",
        primary_metric="cpv",
        primary_target=0.60,
        primary_weight=100,
    )
    spec.metric_baselines = baselines
    m = metrics[2]
    with_baseline = compute_blended_score(m, spec)
    spec.metric_baselines = {}
    without = compute_blended_score(m, spec)
    assert with_baseline != without


def test_weights_must_sum_to_100() -> None:
    spec = StrategySpec(
        mode="blended_2",
        metrics=[
            MetricSpec("cpa", 4.0, 70.0, "minimize"),
            MetricSpec("cpc", 0.1, 29.0, "minimize"),
        ],
        tolerance_band=0.2,
    )
    with pytest.raises(ValueError, match="100"):
        validate_strategy_weights(spec)
