"""Data classes used across the agent.

Kept deliberately simple: dataclasses, no ORM, no pydantic at this stage.
We'll layer validation in when the API client lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def utcnow() -> datetime:
    """Current instant in UTC (timezone-aware)."""

    return datetime.now(timezone.utc)


class ActionReason(str, Enum):
    """Why the engine took (or skipped) a decision on a term.

    These strings are what end up in the weekly digest, so keep them
    short and human-readable in English (we translate to Italian in the
    digest generator)."""

    UNDER_TARGET = "under_target"          # CPV < target → bid up
    OVER_TARGET = "over_target"            # CPV > target → bid down
    ON_TARGET = "on_target"                # within tolerance band
    INSUFFICIENT_VOLUME = "insufficient_volume"
    ANOMALOUS_CTR = "anomalous_ctr"        # click-farm filter
    LOW_VIEWABILITY = "low_viewability"
    ZERO_VISITS = "zero_visits"            # impressions but no visits
    EXPLORATION_REVIVE = "exploration_revive"  # reactivate a zeroed term
    SMOOTHED = "smoothed"                  # delta capped by max step
    CONSTRAINT_VIOLATED = "constraint_violated"


@dataclass
class TermMetric:
    """Performance of a single targeting dimension over the observation window."""

    targeting_module: str           # e.g. "platform"
    targeting_key: str              # e.g. "browser"
    value: str                      # e.g. "Safari"
    field_label: str                # human readable label, e.g. "Safari Browser"

    impressions: int
    clicks: int
    visits: int
    spend: float
    viewable_impressions: int = 0   # optional, 0 means not tracked

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0

    @property
    def visit_rate(self) -> float:
        return self.visits / self.clicks if self.clicks else 0.0

    @property
    def cpv(self) -> float:
        """Cost per visit. Infinity-safe: returns very large number if no visits."""
        if self.visits == 0:
            return float("inf")
        return self.spend / self.visits

    @property
    def viewability(self) -> float:
        if self.impressions == 0:
            return 0.0
        return self.viewable_impressions / self.impressions


@dataclass
class ModifierTerm:
    """Bid modifier term as it lives in Beeswax (subset of v2.0 schema)."""

    targeting_module: str
    targeting_key: str
    value: str
    modifier: float
    modifier_type: str = "include"
    field_label: str = ""

    def to_buzz_payload(self) -> dict[str, Any]:
        """Shape expected by /bid_modifier POST/PUT (v2.0)."""
        return {
            "targeting_module": self.targeting_module,
            "targeting_key": self.targeting_key,
            "value": str(self.value),
            "modifier": round(self.modifier, 3),
            "modifier_type": self.modifier_type,
            "field_label": self.field_label or self.value,
        }

    def key(self) -> tuple[str, str, str]:
        return (self.targeting_module, self.targeting_key, str(self.value))


@dataclass
class ModifierDecision:
    """One decision the engine made on one term."""

    term: ModifierTerm
    previous_modifier: float
    new_modifier: float
    reason: ActionReason
    observed_cpv: float
    observed_impressions: int
    observed_visits: int
    note: str = ""

    @property
    def delta(self) -> float:
        return self.new_modifier - self.previous_modifier

    @property
    def changed(self) -> bool:
        return abs(self.delta) > 0.005


@dataclass
class LineItemChange:
    """Optional changes applied directly on the Line Item bidding block."""

    line_item_id: int
    field: str                      # "max_bid" or "ecpc_target"
    previous_value: float
    new_value: float
    reason: str


@dataclass
class Plan:
    """The full output of one decision pass for a single Line Item."""

    line_item_id: int
    line_item_name: str
    cpv_target: float
    blended_cpv_observed: float
    blended_visits: int
    blended_spend: float
    decisions: list[ModifierDecision] = field(default_factory=list)
    line_item_changes: list[LineItemChange] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)
    week_label: str = ""

    @property
    def changed_decisions(self) -> list[ModifierDecision]:
        return [d for d in self.decisions if d.changed]

    def summary_dict(self) -> dict[str, Any]:
        """Compact summary for logging / digest input."""
        changed = self.changed_decisions
        return {
            "line_item_id": self.line_item_id,
            "line_item_name": self.line_item_name,
            "week_label": self.week_label,
            "cpv_target": self.cpv_target,
            "blended_cpv": self.blended_cpv_observed,
            "blended_visits": self.blended_visits,
            "blended_spend": self.blended_spend,
            "n_terms_evaluated": len(self.decisions),
            "n_terms_changed": len(changed),
            "n_terms_zeroed": sum(1 for d in changed if d.new_modifier == 0),
            "n_terms_boosted": sum(1 for d in changed if d.delta > 0),
            "n_terms_cut": sum(1 for d in changed if d.delta < 0 and d.new_modifier > 0),
            "line_item_changes": [asdict(c) for c in self.line_item_changes],
        }


@dataclass
class HygieneRules:
    """Safety / quality filters applied before any optimization decision."""

    min_impressions_for_action: int = 500
    min_visits_for_strong_action: int = 10
    anomalous_ctr_threshold: float = 0.04   # display benchmark; tune per format
    min_viewability: float = 0.40            # below this → zero the term
    require_viewability_tracking: bool = False


@dataclass
class ActionMetric:
    """Attributed action counts for a term (multi-objective CPA / ROAS)."""

    action_id: str
    weight: float
    value_eur: float
    count: int = 0


@dataclass
class HardConstraintSpec:
    metric: str
    operator: str  # gte | lte
    value: float
    violation_policy: str = "freeze"
    status: str = "active"


@dataclass
class OptimizationProfile:
    """Multi-objective strategy spec (epsilon-constraint path)."""

    profile: str = "minimize_cpv"
    primary_objective_metric: str = "cpv"
    primary_objective_target: float = 0.50
    tolerance_band: float = 0.20


# Backward-compatible alias used during migration from StrategySpec naming.
OptimizationStrategySpec = OptimizationProfile


@dataclass
class ConstraintCheckResult:
    violated: bool
    metric: str
    operator: str
    observed: float
    threshold: float
    policy: str


@dataclass
class OptimizerConfig:
    """Tuneable parameters of the decision engine."""

    cpv_target: float
    tolerance_band: float = 0.20             # ±20% around target = on_target
    max_step_per_run: float = 0.30           # cap delta vs current modifier
    max_modifier: float = 2.5
    min_modifier_active: float = 0.30        # never go below this unless zeroing
    exploration_revive_after_runs: int = 4   # revive zeroed terms after N runs
    exploration_revive_modifier: float = 0.50
    blended_max_bid_step: float = 0.10       # ±10% on max_bid per run
    blended_max_bid_floor: float = 0.50
    blended_max_bid_ceiling: float = 25.0
