"""Blended CPA with two weighted actions."""

from __future__ import annotations

from bidagent.decision_engine import decide_multi_objective
from bidagent.models import (
    ActionMetric,
    ActionReason,
    HygieneRules,
    OptimizationProfile,
    OptimizerConfig,
    TermMetric,
)


def test_blended_cpa() -> None:
    m = TermMetric(
        targeting_module="platform",
        targeting_key="browser",
        value="safari",
        field_label="Safari",
        impressions=5000,
        clicks=50,
        visits=10,
        spend=80.0,
        viewable_impressions=3250,
    )
    actions = [
        ActionMetric("a1", weight=1.0, value_eur=1.0, count=10),
        ActionMetric("a2", weight=8.0, value_eur=7.0, count=5),
    ]
    weighted = 1 * 10 + 8 * 5
    assert weighted == 50
    assert 80.0 / weighted == 1.6

    cfg = OptimizerConfig(cpv_target=0.60, max_step_per_run=0.30)
    hygiene = HygieneRules(min_impressions_for_action=500)
    strategy = OptimizationProfile(
        profile="minimize_blended_cpa",
        primary_objective_metric="blended_cpa",
        primary_objective_target=2.5,
        tolerance_band=0.20,
    )
    plan = decide_multi_objective(
        1,
        "LI",
        "2026-W01",
        [m],
        {("platform", "browser", "safari"): 1.0},
        {},
        5.0,
        cfg,
        hygiene,
        strategy=strategy,
        actions_by_term={("platform", "browser", "safari"): actions},
    )
    assert plan.decisions[0].reason == ActionReason.UNDER_TARGET
