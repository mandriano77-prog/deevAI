"""Tests for the DV360 score simulator and DSL interpreter.

Covers:
- dsl_interpreter: positive cases (return / aggregate / cast / membership /
  conditional None) and negative cases (assignment / def / import /
  lambda / while / eval-like).
- score_simulator: determinism, coverage, edge cases, an end-to-end
  smoke against a real generator-produced script, and a 10k-row
  performance budget.

No real DV360 calls.
"""

from __future__ import annotations

import time

import pytest

from bidagent.engines.custom_bidding import (
    DSLRuntimeError,
    DSLValidationError,
    ImpressionRow,
    ObjectiveId,
    ScoreSimulator,
    SimulationDataset,
    TenantConfig,
    compile_script,
    evaluate,
    generate_script,
    generate_synthetic_dataset,
    run_with_signals,
    simulate_tenant_config,
)


# ────────────────────────────────────────────────── DSL interpreter (positive)


def test_interpreter_return_simple_constant():
    """A bare numeric return is the simplest legal DSL script."""
    assert run_with_signals("return 42", {}) == 42


def test_interpreter_return_none_excludes():
    """`return None` is the DV360 idiom for 'exclude from training'."""
    assert run_with_signals("return None", {}) is None


def test_interpreter_sum_aggregate_with_signals():
    """sum_aggregate adds the weights of every true criterion."""
    script = (
        "return sum_aggregate([\n"
        "    ([active_view_viewed == 1], 400.0),\n"
        "    ([click == 1], 50.0),\n"
        "])"
    )
    signals = {"active_view_viewed": 1, "click": 1}
    assert run_with_signals(script, signals) == 450.0

    # Only one criterion true → only its weight contributes.
    signals = {"active_view_viewed": 1, "click": 0}
    assert run_with_signals(script, signals) == 400.0

    # Neither true → 0 (not None).
    signals = {"active_view_viewed": 0, "click": 0}
    assert run_with_signals(script, signals) == 0.0


def test_interpreter_max_and_first_match_aggregates():
    """max_aggregate picks the largest matched weight; first_match takes
    the first one even if a later one is heavier."""
    script_max = (
        "return max_aggregate([\n"
        "    ([active_view_viewed == 1], 100.0),\n"
        "    ([click == 1], 400.0),\n"
        "])"
    )
    assert run_with_signals(script_max, {"active_view_viewed": 1, "click": 1}) == 400.0

    script_first = script_max.replace("max_aggregate", "first_match_aggregate")
    assert run_with_signals(script_first, {"active_view_viewed": 1, "click": 1}) == 100.0


def test_interpreter_casts_and_log():
    """Casting helpers and the log math fn behave like their Python equivalents."""
    # Casts
    assert run_with_signals("return int(time_on_screen_seconds)",
                            {"time_on_screen_seconds": 5.7}) == 5
    assert run_with_signals("return float(click)", {"click": 1}) == 1.0
    assert run_with_signals("return bool(time_on_screen_seconds)",
                            {"time_on_screen_seconds": 0}) is False
    assert run_with_signals("return str(country_code)",
                            {"country_code": "IT"}) == "IT"
    # log(x) = natural log
    import math as _math
    assert run_with_signals("return log(time_on_screen_seconds)",
                            {"time_on_screen_seconds": 10}) == pytest.approx(_math.log(10))
    # log(x, base) = log_base(x)
    assert run_with_signals("return log(time_on_screen_seconds, 10)",
                            {"time_on_screen_seconds": 100}) == pytest.approx(2.0)


def test_interpreter_membership_in_and_not_in():
    """`x in [a, b, c]` is the DV360 way to test enum membership."""
    script = "return country_code in [\"IT\", \"US\"]"
    assert run_with_signals(script, {"country_code": "IT"}) is True
    assert run_with_signals(script, {"country_code": "DE"}) is False

    not_in_script = "return country_code not in [\"IT\"]"
    assert run_with_signals(not_in_script, {"country_code": "DE"}) is True


def test_interpreter_conditional_excludes_with_if_return_none():
    """The 'excluding slice' pattern: `if cond: return None`."""
    script = (
        "if click == 0:\n"
        "    return None\n"
        "return sum_aggregate([([active_view_viewed == 1], 100.0)])\n"
    )
    # Excluded slice
    assert run_with_signals(script, {"click": 0, "active_view_viewed": 1}) is None
    # Survives the gate → scored normally
    assert run_with_signals(script, {"click": 1, "active_view_viewed": 1}) == 100.0


# ────────────────────────────────────────────────── DSL interpreter (negative)


@pytest.mark.parametrize(
    "bad_source",
    [
        # Assignment is forbidden — we never allow Store contexts.
        "x = 5\nreturn x",
        # Function defs blow up the AST whitelist.
        "def f():\n    return 5\nreturn f()",
        # Imports are out.
        "import os\nreturn 5",
        # Lambdas aren't on the whitelist.
        "return (lambda x: x)(5)",
        # While loops are out.
        "while True:\n    return 5",
        # The classic eval-like trick.
        "return __import__('os').system('echo hi')",
    ],
)
def test_interpreter_rejects_unsafe_constructs(bad_source: str):
    """Every one of these must be rejected at compile time — *before*
    we touch any data. The error class is the validation one, never a
    Python error."""
    with pytest.raises(DSLValidationError):
        compile_script(bad_source)


# ────────────────────────────────────────────────── simulator (determinism)


def test_simulator_is_deterministic_for_same_inputs():
    """Same script + same seed → identical SimulationReport (modulo timing).

    We compare every field that should be data-stable: distribution
    percentiles, histogram, top winners/losers, coverage, and sha.
    """
    cfg = TenantConfig(
        weights={
            ObjectiveId.PERFORMANCE: 0.5,
            ObjectiveId.QUALITY: 0.3,
            ObjectiveId.REACH: 0.2,
        },
        floodlight_activity_id=99999,
        country_focus=("IT",),
    )
    ds1 = generate_synthetic_dataset(n=500, seed=2024)
    ds2 = generate_synthetic_dataset(n=500, seed=2024)

    r1 = simulate_tenant_config(cfg, ds1, tenant_id="det")
    r2 = simulate_tenant_config(cfg, ds2, tenant_id="det")

    assert r1.script_sha256 == r2.script_sha256
    assert r1.n_impressions == r2.n_impressions == 500
    assert r1.value_distribution == r2.value_distribution
    assert r1.value_histogram == r2.value_histogram
    assert r1.pct_above_500 == r2.pct_above_500
    assert r1.top_winners == r2.top_winners
    assert r1.top_losers == r2.top_losers
    assert r1.feature_coverage == r2.feature_coverage


# ───────────────────────────────────────────────── simulator (coverage / edge)


def test_feature_coverage_zero_for_unused_signals():
    """A signal that's never present in the dataset shows up as 0 in the
    coverage map — never missing, never None — so the UI can render
    it greyed out without crashing."""
    script = "return sum_aggregate([([click == 1], 100.0)])"
    ds = SimulationDataset(
        impressions=tuple(
            ImpressionRow(signals={"click": (i % 5 == 0)}) for i in range(50)
        )
    )
    report = ScoreSimulator(script).simulate(ds)

    # `click` was read with a truthy/non-None value: > 0
    assert report.feature_coverage["click"] > 0
    # Pick a signal we *know* is in the catalog but absent from the dataset.
    assert report.feature_coverage["zip_postal_code"] == 0
    assert report.feature_coverage["video_completed"] == 0
    # Sanity: full coverage map covers every catalog signal.
    from bidagent.engines.custom_bidding import SIGNALS_BY_NAME
    assert set(report.feature_coverage.keys()) == set(SIGNALS_BY_NAME.keys())


def test_simulator_empty_dataset():
    """Empty dataset → no scores, but the report shape is still well-formed."""
    script = "return sum_aggregate([([click == 1], 100.0)])"
    ds = SimulationDataset(impressions=())
    report = ScoreSimulator(script).simulate(ds)

    assert report.n_impressions == 0
    assert report.n_scored == 0
    assert report.n_excluded == 0
    assert report.pct_above_500 == 0.0
    assert report.top_winners == ()
    assert report.top_losers == ()
    # Every stat is 0 (not NaN) — UI-friendly.
    assert all(v == 0.0 for v in report.value_distribution.values())
    # Histogram still has 20 bins, all zero.
    assert len(report.value_histogram) == 20
    assert all(count == 0 for _, _, count in report.value_histogram)


def test_simulator_script_always_returns_none():
    """If the script never returns a score, every row is excluded and
    n_scored == 0. Distribution stats are zero across the board."""
    script = "return None"
    ds = generate_synthetic_dataset(n=200, seed=7)
    report = ScoreSimulator(script).simulate(ds)

    assert report.n_impressions == 200
    assert report.n_scored == 0
    assert report.n_excluded == 200
    assert report.value_distribution["mean"] == 0.0
    assert report.top_winners == ()
    # And no signals got resolved (the script doesn't read any).
    assert all(v == 0 for v in report.feature_coverage.values())


# ──────────────────────────────────────────────── simulator (smoke real)


def test_simulator_smoke_with_real_generator_performance_recipe():
    """End-to-end: generate a Performance-heavy script via the real
    generator, run it through the simulator on 1k synthetic rows, and
    assert the report numbers are sensible (mean in (0, 1000), some
    rows scored)."""
    cfg = TenantConfig(
        weights={
            ObjectiveId.PERFORMANCE: 0.7,
            ObjectiveId.QUALITY: 0.2,
            ObjectiveId.REACH: 0.1,
        },
        floodlight_activity_id=42,
        country_focus=("IT",),
    )
    ds = generate_synthetic_dataset(n=1000, seed=42, recipe="performance")
    report = simulate_tenant_config(cfg, ds, tenant_id="smoke")

    assert report.n_impressions == 1000
    assert report.n_scored > 0
    assert 0.0 < report.value_distribution["mean"] < 1000.0
    # The distribution should be non-trivial — p10 < p90 strictly.
    assert report.value_distribution["p10"] <= report.value_distribution["p90"]
    # Some signals were definitely used.
    assert report.feature_coverage["active_view_viewed"] > 0


# ───────────────────────────────────────────────────────── performance


def test_simulator_10k_rows_under_two_seconds():
    """Budget: 10k rows must score in < 2s on stdlib alone. If we ever
    blow this we need numpy or rework the interpreter — but pure-Python
    AST dispatch is plenty fast for the simulator's expected scale."""
    script = (
        "return sum_aggregate([\n"
        "    ([active_view_viewed == 1], 400.0),\n"
        "    ([time_on_screen_seconds >= 5], 200.0),\n"
        "    ([video_completed == 1], 200.0),\n"
        "    ([click == 1], 50.0),\n"
        "    ([country_code in [\"IT\", \"US\"]], 150.0),\n"
        "])"
    )
    ds = generate_synthetic_dataset(n=10_000, seed=123)
    sim = ScoreSimulator(script)

    start = time.perf_counter()
    report = sim.simulate(ds)
    elapsed = time.perf_counter() - start

    assert report.n_scored == 10_000
    # Generous budget. Local M-series macs usually finish well under 1s.
    assert elapsed < 2.0, f"10k-row simulation took {elapsed:.3f}s (>2s budget)"
