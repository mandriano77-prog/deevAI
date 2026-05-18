"""CPC above threshold + freeze policy → no movement."""

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


def test_constraint_freeze() -> None:
    m = TermMetric(
        targeting_module="platform",
        targeting_key="browser",
        value="safari",
        field_label="Safari",
        impressions=5000,
        clicks=200,
        visits=20,
        spend=40.0,
        viewable_impressions=3250,
    )
    cfg = OptimizerConfig(cpv_target=0.60, max_step_per_run=0.30)
    hygiene = HygieneRules(min_impressions_for_action=500, require_viewability_tracking=False)
    constraints = [
        HardConstraintSpec(metric="cpc", operator="lte", value=0.15, violation_policy="freeze"),
    ]
    plan = decide_multi_objective(
        1,
        "LI",
        "2026-W01",
        [m],
        {("platform", "browser", "safari"): 1.2},
        {},
        5.0,
        cfg,
        hygiene,
        strategy=OptimizationProfile(profile="minimize_cpv", primary_objective_target=0.60),
        constraints=constraints,
    )
    d = plan.decisions[0]
    assert d.reason == ActionReason.CONSTRAINT_VIOLATED
    assert d.new_modifier == 1.2
