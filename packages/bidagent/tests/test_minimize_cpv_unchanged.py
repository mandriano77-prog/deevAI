"""profile=minimize_cpv with no constraints → same output as legacy decide()."""

from __future__ import annotations

from bidagent.decision_engine import build_plan, decide_multi_objective
from bidagent.models import HygieneRules, OptimizerConfig, TermMetric


def _metric() -> TermMetric:
    return TermMetric(
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


def test_minimize_cpv_unchanged() -> None:
    cfg = OptimizerConfig(cpv_target=0.60, tolerance_band=0.20, max_step_per_run=0.30)
    hygiene = HygieneRules(min_impressions_for_action=500)
    metrics = [_metric()]
    mods = {("platform", "browser", "safari"): 1.0}
    runs: dict = {}

    legacy = build_plan(
        1, "LI", "2026-W01", metrics, mods, runs, 5.0, cfg, hygiene,
    )
    multi = decide_multi_objective(
        1, "LI", "2026-W01", metrics, mods, runs, 5.0, cfg, hygiene,
    )
    assert len(legacy.decisions) == len(multi.decisions)
    for a, b in zip(legacy.decisions, multi.decisions, strict=True):
        assert a.new_modifier == b.new_modifier
        assert a.reason == b.reason
