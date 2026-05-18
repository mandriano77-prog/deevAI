"""Metric direction helpers for metric-agnostic optimization."""

from __future__ import annotations

from typing import Literal

MetricName = Literal[
    "cpv", "cpc", "cpcv", "cpm", "cpa", "roas", "custom_action",
]
StrategyMode = Literal["single", "blended_2", "blended_3"]
MetricDirection = Literal["minimize", "maximize"]

MINIMIZE_METRICS = frozenset({"cpv", "cpc", "cpcv", "cpm", "cpa"})
MAXIMIZE_METRICS = frozenset({"roas", "custom_action"})

ALLOWED_METRICS = MINIMIZE_METRICS | MAXIMIZE_METRICS


def metric_direction(metric: str) -> MetricDirection:
    if metric in MINIMIZE_METRICS:
        return "minimize"
    if metric in MAXIMIZE_METRICS:
        return "maximize"
    raise ValueError(f"Unknown metric: {metric}")
