#!/usr/bin/env python3
"""Standalone smoke for the deevAI score simulator.

Run it from the bidagent package root::

    cd packages/bidagent
    .venv/bin/python scripts/smoke_score_simulator.py

It will:
  1. Build a TenantConfig with the canonical sliders [70, 20, 10]
     (Performance / Quality / Reach).
  2. Generate the DV360 DSL script via :func:`generate_script`.
  3. Generate 5 000 synthetic impressions with a "performance" profile.
  4. Run the script through :class:`ScoreSimulator`.
  5. Print:
        - the generated DSL source,
        - distribution stats (mean / stddev / percentiles / pct >500),
        - top-5 winners and top-5 losers with their breakdowns,
        - per-signal coverage counts (non-zero only).

No network. No DV360 calls. Pure local sanity check.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Make the smoke runnable without installing the package: prepend the
# bidagent source tree to sys.path. The script lives in
# packages/bidagent/scripts/, so the package root is two levels up.
_HERE = Path(__file__).resolve()
_PKG_SRC = _HERE.parent.parent  # packages/bidagent
if str(_PKG_SRC) not in sys.path:
    sys.path.insert(0, str(_PKG_SRC))

from bidagent.engines.custom_bidding import (  # noqa: E402 — sys.path tweak above
    ObjectiveId,
    ScoreSimulator,
    TenantConfig,
    generate_script,
    generate_synthetic_dataset,
)


def _format_pct(p: float) -> str:
    return f"{p:6.2f}%"


def _format_score(s: float | None) -> str:
    return "    --" if s is None else f"{s:7.2f}"


def main() -> int:
    # Slider preset: [70, 20, 10] → mostly Performance.
    cfg = TenantConfig(
        weights={
            ObjectiveId.PERFORMANCE: 0.70,
            ObjectiveId.QUALITY: 0.20,
            ObjectiveId.REACH: 0.10,
        },
        floodlight_activity_id=12345678,
        country_focus=("IT",),
    )

    print("=" * 72)
    print("deevAI Score Simulator — smoke run")
    print("=" * 72)

    # ─── 1. Generate the DSL script
    script = generate_script(cfg, tenant_id="smoke-tenant")
    print()
    print(f"Generated script ({len(script.source.encode())} bytes, "
          f"sha256={script.digest_sha256[:12]}…):")
    print("-" * 72)
    print(script.source)

    # ─── 2. Build a synthetic dataset (5k rows, deterministic seed)
    n = 5_000
    print(f"Generating {n:,} synthetic impressions (recipe=performance, seed=2024)…")
    t0 = time.perf_counter()
    dataset = generate_synthetic_dataset(n=n, seed=2024, recipe="performance")
    t_gen = time.perf_counter() - t0
    print(f"  done in {t_gen*1000:.1f} ms")

    # ─── 3. Simulate
    print("Running ScoreSimulator…")
    t0 = time.perf_counter()
    sim = ScoreSimulator(script.source)
    report = sim.simulate(dataset)
    t_sim = time.perf_counter() - t0
    print(f"  done in {t_sim*1000:.1f} ms "
          f"({n/t_sim:,.0f} rows/s)")

    # ─── 4. Print the report
    dist = report.value_distribution
    print()
    print("Distribution")
    print("-" * 72)
    print(f"  n_impressions  : {report.n_impressions:>8,}")
    print(f"  n_scored       : {report.n_scored:>8,}")
    print(f"  n_excluded     : {report.n_excluded:>8,}")
    print(f"  mean           : {dist['mean']:>8.2f}")
    print(f"  stddev         : {dist['stddev']:>8.2f}")
    print(f"  p10 / p50 / p90: {dist['p10']:>6.1f} / {dist['p50']:>6.1f} / {dist['p90']:>6.1f}")
    print(f"  p99            : {dist['p99']:>8.2f}")
    print(f"  % > 500        : {_format_pct(report.pct_above_500)}")

    print()
    print("Top 5 winners")
    print("-" * 72)
    for w in report.top_winners[:5]:
        sig_preview = ", ".join(w.used_signals[:6])
        if len(w.used_signals) > 6:
            sig_preview += f", +{len(w.used_signals) - 6} more"
        print(f"  {w.impression_id:>14}  score={_format_score(w.score)}  "
              f"signals=[{sig_preview}]")

    print()
    print("Top 5 losers")
    print("-" * 72)
    for losers in report.top_losers[:5]:
        sig_preview = ", ".join(losers.used_signals[:6])
        if len(losers.used_signals) > 6:
            sig_preview += f", +{len(losers.used_signals) - 6} more"
        print(f"  {losers.impression_id:>14}  score={_format_score(losers.score)}  "
              f"signals=[{sig_preview}]")

    # Coverage summary — only signals that appeared somewhere.
    used_cov = {k: v for k, v in report.feature_coverage.items() if v > 0}
    print()
    print(f"Feature coverage (signals seen non-None at least once: {len(used_cov)})")
    print("-" * 72)
    for sig, count in sorted(used_cov.items(), key=lambda kv: -kv[1]):
        bar = "█" * int(40 * count / report.n_impressions)
        print(f"  {sig:<32} {count:>6,} {bar}")

    print()
    print("OK — smoke completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
