"""Score-distribution simulator for DV360 Custom Bidding scripts.

What it does
------------
Given a DV360 custom-bidding script and a batch of historical
impressions (each with its signal values), the simulator runs the
script *locally* through the sandboxed :mod:`dsl_interpreter` and
returns a :class:`SimulationReport` describing the score distribution.

Why we want it
--------------
DV360 only exposes the score behaviour of a script *after* you upload
it and let real money run through it. That feedback loop is too slow
for a slider UI. With the simulator the customer can move the three
Performance/Quality/Reach sliders, see the score distribution
*immediately* on their historical Floodlight rows, and ship only when
the curve looks right.

Inputs
~~~~~~
- ``script``: the raw DSL source (the same bytes we'd upload).
- ``dataset``: a :class:`SimulationDataset` containing one signal-dict
  per impression. Signals are referenced *by name* (the catalog name),
  e.g. ``"active_view_viewed"`` → 1.

Outputs
~~~~~~~
- ``SimulationReport``: distribution stats, histogram, top-20
  winners/losers with their score *and* the signals that mattered.

Security
~~~~~~~~
The script is never ``eval``-ed or ``exec``-uted. It is parsed once,
validated by the sandbox validator, and interpreted via AST dispatch.
See :mod:`dsl_interpreter` for the security model.

Determinism
~~~~~~~~~~~
Given the same script + same dataset + same Python (no
``microsecond=...`` shenanigans), the report is bit-stable: histogram
bins, top-20 ordering, sha256 — all reproducible. The synthetic
dataset generator uses an explicit seed so it's reproducible too.
"""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping

from .dsl_interpreter import (
    CompiledScript,
    DSLError,
    DSLRuntimeError,
    SignalResolver,
    compile_script,
    evaluate,
)
from .feature_catalog import SIGNALS_BY_NAME
from .objectives import ObjectiveId, TenantConfig
from .script_generator import generate_script


# ─────────────────────────────────────────────────────────────── dataclasses


@dataclass(frozen=True)
class ImpressionRow:
    """One historical impression we want to score.

    ``signals`` maps DV360-catalog signal names to their value for this
    row. Missing keys = "not measured for this impression" — the
    interpreter resolves them as None.

    For callable signals (e.g. ``total_conversion_value``) the value
    can be a Python callable or a constant. A constant is returned
    verbatim regardless of args; a callable is called with the args
    DV360 would have passed.

    ``impression_id`` is opaque — used purely to identify rows in the
    top winners/losers report. Defaults to the row index.
    """
    signals: Mapping[str, Any]
    impression_id: str | None = None


@dataclass(frozen=True)
class ImpressionScoreBreakdown:
    """One row in the top-winners / top-losers report.

    We include the resolved signals that mattered (used_signals) so the
    UI can render an explanation tooltip without re-running the script.
    """
    impression_id: str
    score: float | None
    used_signals: tuple[str, ...]


@dataclass(frozen=True)
class SimulationDataset:
    """The set of impressions to simulate against."""
    impressions: tuple[ImpressionRow, ...]


# ────────────────────────────────────────────────────────────────── report


# Fixed list of percentiles so the report shape is stable for the UI.
_PCT_KEYS: tuple[tuple[str, float], ...] = (
    ("p10", 0.10),
    ("p25", 0.25),
    ("p50", 0.50),
    ("p75", 0.75),
    ("p90", 0.90),
    ("p99", 0.99),
)

_HIST_BINS: int = 20  # 0..1000 in 50-wide bins is the DV360 default

_TOP_N: int = 20  # winners + losers slice size


@dataclass(frozen=True)
class SimulationReport:
    """The simulator's verdict on a (script, dataset) pair."""
    n_impressions: int
    n_scored: int
    n_excluded: int
    value_distribution: dict[str, float]
    value_histogram: tuple[tuple[float, float, int], ...]
    pct_above_500: float
    top_winners: tuple[ImpressionScoreBreakdown, ...]
    top_losers: tuple[ImpressionScoreBreakdown, ...]
    script_sha256: str
    feature_coverage: dict[str, int]


# ─────────────────────────────────────────────────────────────── simulator


class ScoreSimulator:
    """Run a DV360 DSL script against a batch of impressions.

    The simulator is stateless after construction — re-use across
    datasets is supported and encouraged (parse-once, run-many).
    """

    def __init__(self, script: str) -> None:
        """Compile the script once.

        Raises :class:`dsl_interpreter.DSLValidationError` if the script
        doesn't pass the static sandbox check. We *want* this to be
        loud — running an invalid script through the interpreter would
        only repeat the same error per impression.
        """
        self._source = script
        self._compiled: CompiledScript = compile_script(script)
        self._sha256 = hashlib.sha256(script.encode("utf-8")).hexdigest()

    # ─────────────────────────────────── public API

    @property
    def script_sha256(self) -> str:
        return self._sha256

    def simulate(self, dataset: SimulationDataset) -> SimulationReport:
        """Run the script for every impression and assemble the report."""
        n_impressions = len(dataset.impressions)
        scored_values: list[tuple[int, float]] = []  # (idx, value)
        n_excluded = 0
        coverage: Counter[str] = Counter()
        breakdowns: dict[int, tuple[str, ...]] = {}

        for idx, row in enumerate(dataset.impressions):
            resolver = _make_resolver(row.signals)
            try:
                value, used, used_non_none = evaluate(self._compiled, resolver)
            except DSLRuntimeError:
                # Runtime errors per-row are treated as "exclude" rather
                # than aborting the whole simulation — one bad row
                # shouldn't blow up a 10k-row report. We still surface
                # the failure via coverage counters being unaffected.
                n_excluded += 1
                continue

            for sig in used_non_none:
                coverage[sig] += 1

            if value is None:
                n_excluded += 1
            else:
                try:
                    fv = float(value)
                except (TypeError, ValueError):
                    # Script returned something non-numeric — treat as
                    # exclude for simulator purposes (DV360 would do
                    # the same at runtime).
                    n_excluded += 1
                    continue
                # NaN / inf handling — count as excluded to avoid
                # poisoning the distribution stats.
                if not math.isfinite(fv):
                    n_excluded += 1
                    continue
                scored_values.append((idx, fv))
                breakdowns[idx] = tuple(sorted(used_non_none))

        n_scored = len(scored_values)

        return SimulationReport(
            n_impressions=n_impressions,
            n_scored=n_scored,
            n_excluded=n_excluded,
            value_distribution=_distribution_stats([v for _, v in scored_values]),
            value_histogram=_histogram([v for _, v in scored_values]),
            pct_above_500=_pct_above(scored_values, 500.0),
            top_winners=_top_n(scored_values, dataset, breakdowns, reverse=True),
            top_losers=_top_n(scored_values, dataset, breakdowns, reverse=False),
            script_sha256=self._sha256,
            feature_coverage=_full_coverage(coverage),
        )


# ──────────────────────────────────────────────────────────── helpers


def _make_resolver(signals: Mapping[str, Any]) -> SignalResolver:
    """Adapter: per-row signal dict → SignalResolver callable.

    Callable-style signals can be supplied as a Python callable in the
    dict; we forward whatever args DV360 would pass. Plain values are
    returned verbatim — handy for synthetic tests where conversion
    values are pre-computed per row.
    """
    def resolver(name: str, args: tuple[Any, ...]) -> Any:
        if name not in signals:
            return None
        v = signals[name]
        if callable(v):
            try:
                return v(*args)
            except TypeError:
                # Caller supplied a 0-arity callable but DV360 passed
                # args — fall back to the value itself.
                return v()
        return v
    return resolver


def _distribution_stats(values: list[float]) -> dict[str, float]:
    """Compute the canonical distribution stats.

    Empty list → every stat is 0.0 (and not NaN) so the UI doesn't
    have to special-case it.
    """
    if not values:
        return {
            **{key: 0.0 for key, _ in _PCT_KEYS},
            "mean": 0.0,
            "stddev": 0.0,
        }

    sorted_values = sorted(values)
    stats: dict[str, float] = {}
    for key, q in _PCT_KEYS:
        stats[key] = _percentile(sorted_values, q)

    stats["mean"] = statistics.fmean(values)
    stats["stddev"] = statistics.pstdev(values) if len(values) > 1 else 0.0
    return stats


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated percentile (numpy's "linear" method).

    We avoid numpy because the dependency floor is stdlib-only — and
    a manual implementation is six lines, fully tested.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_values[lo])
    frac = pos - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def _histogram(values: list[float]) -> tuple[tuple[float, float, int], ...]:
    """20-bin histogram over [0, 1000] (DV360's score domain).

    Each bin is ``(lo, hi, count)``. Values < 0 are clamped to bin 0,
    values > 1000 to the last bin — this matches DV360's score
    quantisation.
    """
    bin_width = 1000.0 / _HIST_BINS
    counts = [0] * _HIST_BINS
    for v in values:
        if v <= 0:
            counts[0] += 1
            continue
        if v >= 1000:
            counts[-1] += 1
            continue
        idx = min(int(v // bin_width), _HIST_BINS - 1)
        counts[idx] += 1
    return tuple(
        (i * bin_width, (i + 1) * bin_width, counts[i])
        for i in range(_HIST_BINS)
    )


def _pct_above(scored: list[tuple[int, float]], threshold: float) -> float:
    if not scored:
        return 0.0
    n_above = sum(1 for _, v in scored if v > threshold)
    return 100.0 * n_above / len(scored)


def _top_n(
    scored: list[tuple[int, float]],
    dataset: SimulationDataset,
    breakdowns: dict[int, tuple[str, ...]],
    reverse: bool,
) -> tuple[ImpressionScoreBreakdown, ...]:
    """Top-N winners (reverse=True) or losers (reverse=False).

    Ties are broken by original impression index so the output is
    deterministic for repeated runs over the same dataset.
    """
    if not scored:
        return ()
    # Sort by (-value, idx) for winners; (value, idx) for losers. Using
    # idx as tiebreaker keeps the order stable.
    if reverse:
        ranked = sorted(scored, key=lambda kv: (-kv[1], kv[0]))
    else:
        ranked = sorted(scored, key=lambda kv: (kv[1], kv[0]))
    out: list[ImpressionScoreBreakdown] = []
    for idx, value in ranked[:_TOP_N]:
        row = dataset.impressions[idx]
        imp_id = row.impression_id or f"row#{idx}"
        out.append(ImpressionScoreBreakdown(
            impression_id=imp_id,
            score=value,
            used_signals=breakdowns.get(idx, ()),
        ))
    return tuple(out)


def _full_coverage(coverage: Counter[str]) -> dict[str, int]:
    """Return coverage for *every* catalog signal — zero where unused.

    The UI uses this to render the signal-picker with grey-out for
    signals that didn't appear in the dataset (= can't be relied upon
    by the script).
    """
    out = {name: 0 for name in SIGNALS_BY_NAME}
    out.update(coverage)
    return out


# ────────────────────────────────────────── synthetic dataset generator


# Realistic-ish marginal distributions for the most-used signals. Numbers
# are picked from ballpark industry references (IAB viewability ~55%,
# VTR ~70%, etc.) — they're not pulled from real Floodlight rows but
# they're plausible enough to drive a useful smoke / demo.
_SYNTHETIC_PROFILES: dict[str, dict[str, Any]] = {
    "performance": {
        # 8% click rate, 1.5% conv count, 0.8% conv with revenue
        "click_p": 0.08,
        "conv_count_p": 0.015,
        "conv_rev_p": 0.008,
        "viewable_p": 0.55,
        "video_completed_p": 0.55,
        "time_on_screen_lambda": 0.18,  # mean ≈ 5.5s
    },
    "quality": {
        "click_p": 0.03,
        "conv_count_p": 0.005,
        "conv_rev_p": 0.002,
        "viewable_p": 0.70,
        "video_completed_p": 0.75,
        "time_on_screen_lambda": 0.12,  # mean ≈ 8.3s
    },
    "reach": {
        "click_p": 0.015,
        "conv_count_p": 0.002,
        "conv_rev_p": 0.0005,
        "viewable_p": 0.45,
        "video_completed_p": 0.40,
        "time_on_screen_lambda": 0.25,  # mean ≈ 4s
    },
}


def generate_synthetic_dataset(
    n: int = 10_000,
    *,
    seed: int = 42,
    recipe: str = "performance",
    floodlight_activity_id: int = 12345,
) -> SimulationDataset:
    """Generate ``n`` plausible impressions for smoke tests.

    The distributions match rough industry benchmarks per ``recipe``
    profile ("performance" / "quality" / "reach"). The point isn't
    statistical realism — it's giving the simulator enough variance to
    produce a meaningful score curve without needing real DV360 data.

    Determinism: same ``seed`` → same dataset, regardless of host.

    Layout per impression:
      - ``active_view_viewed`` (0/1) — bernoulli
      - ``time_on_screen_seconds`` (int ≥ 0) — exponential
      - ``ad_position`` (0|1|2) — 50% above-the-fold
      - ``video_completed`` (0/1) — bernoulli (only meaningful for
        ad_type=1 impressions; we still emit for all rows because real
        DV360 returns 0 for non-video too)
      - ``click`` (0/1)
      - ``country_code`` — IT/US/DE/FR/UK weighted
      - ``device_type`` — desktop / smartphone / connected_tv
      - ``hour_of_day`` — uniform 0..23 with a daytime bias
      - ``total_conversion_value(activity, model)`` — callable, returns
        a Pareto-ish revenue for the small fraction of converters
      - ``total_conversion_count(activity, model)`` — callable
    """
    if recipe not in _SYNTHETIC_PROFILES:
        raise ValueError(
            f"Unknown synthetic recipe {recipe!r}; "
            f"available: {sorted(_SYNTHETIC_PROFILES)}"
        )
    profile = _SYNTHETIC_PROFILES[recipe]
    rng = random.Random(seed)

    rows: list[ImpressionRow] = []
    for i in range(n):
        viewable = 1 if rng.random() < profile["viewable_p"] else 0
        # Exponential-ish time on screen
        tos = int(rng.expovariate(profile["time_on_screen_lambda"]))
        tos = min(tos, 120)  # cap at 2 minutes — anything more is bot-like
        above_fold = 1 if rng.random() < 0.5 else (2 if rng.random() < 0.7 else 0)
        video_completed = 1 if rng.random() < profile["video_completed_p"] else 0
        click = 1 if rng.random() < profile["click_p"] else 0
        country = rng.choices(
            ["IT", "US", "DE", "FR", "UK"],
            weights=[0.45, 0.20, 0.15, 0.12, 0.08],
        )[0]
        device = rng.choices(
            [0, 2, 5],  # desktop, smartphone, connected_tv
            weights=[0.35, 0.50, 0.15],
        )[0]
        # Daytime-biased hour
        hour = rng.choices(
            list(range(24)),
            weights=[
                0.01, 0.005, 0.005, 0.005, 0.005, 0.01,
                0.02, 0.03, 0.05, 0.06, 0.07, 0.08,
                0.08, 0.07, 0.07, 0.07, 0.06, 0.07,
                0.08, 0.08, 0.07, 0.05, 0.03, 0.02,
            ],
        )[0]

        # Conversion outcomes — most rows are 0.
        if rng.random() < profile["conv_rev_p"]:
            # Pareto-ish revenue: tons of small purchases, occasional big.
            conv_value = round(rng.paretovariate(1.4) * 12.0, 2)
            conv_count = 1.0
        elif rng.random() < profile["conv_count_p"]:
            conv_value = 0.0
            conv_count = 1.0
        else:
            conv_value = 0.0
            conv_count = 0.0

        signals: dict[str, Any] = {
            "active_view_viewed": viewable,
            "time_on_screen_seconds": tos,
            "ad_position": above_fold,
            "video_completed": video_completed,
            "click": click,
            "country_code": country,
            "device_type": device,
            "hour_of_day": hour,
            # Callable signals — DV360 passes (activity_id, model_id).
            # We ignore them; the row already encodes the outcome.
            "total_conversion_value": (lambda _a=conv_value: lambda *_args: _a)(),
            "total_conversion_count": (lambda _c=conv_count: lambda *_args: _c)(),
        }
        rows.append(ImpressionRow(signals=signals, impression_id=f"syn-{i:06d}"))

    return SimulationDataset(impressions=tuple(rows))


# ──────────────────────────────────────────── convenience for tests/UI


def simulate_tenant_config(
    cfg: TenantConfig,
    dataset: SimulationDataset,
    *,
    tenant_id: str = "simulator",
) -> SimulationReport:
    """End-to-end shortcut: generate the script from a TenantConfig then
    simulate it.

    Useful from the UI (slider → preview) and from the smoke script.
    Returns the same SimulationReport as :meth:`ScoreSimulator.simulate`.
    """
    script = generate_script(cfg, tenant_id=tenant_id)
    sim = ScoreSimulator(script.source)
    return sim.simulate(dataset)
