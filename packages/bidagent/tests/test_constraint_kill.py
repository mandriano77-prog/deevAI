"""Viewability below threshold + kill policy → modifier 0."""

from __future__ import annotations

from bidagent.decision_engine import decide_multi_objective
from bidagent.models import (
    ActionReason,
    HardConstraintSpec,
    HygieneRules,
    OptimizationProfile,
    OptimizerConfig,
    TermMetric,
)


def test_constraint_kill() -> None:
    m = TermMetric(
        targeting_module="platform",
        targeting_key="browser",
        value="safari",
        field_label="Safari",
        impressions=8000,
        clicks=50,
        visits=40,
        spend=20.0,
        viewable_impressions=2400,
    )
    cfg = OptimizerConfig(cpv_target=0.60, max_step_per_run=0.30)
    hygiene = HygieneRules(
        min_impressions_for_action=500,
        min_viewability=0.10,
        require_viewability_tracking=False,
    )
    constraints = [
        HardConstraintSpec(
            metric="viewability", operator="gte", value=0.50, violation_policy="kill",
        ),
    ]
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
        strategy=OptimizationProfile(profile="minimize_cpv", primary_objective_target=0.60),
        constraints=constraints,
    )
    assert plan.decisions[0].new_modifier == 0.0
    assert plan.decisions[0].reason == ActionReason.CONSTRAINT_VIOLATED
