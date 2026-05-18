"""Pydantic schemas for HardConstraint with metric/operator validation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import ApiModel

ConstraintMetric = Literal[
    "cpc",
    "cpm",
    "cpcv",
    "vtr",
    "viewability",
    "fraud_rate",
    "roas",
    "revenue_per_day",
    "volume_per_day",
]
ConstraintOperator = Literal["gte", "lte"]
ViolationPolicy = Literal["freeze", "throttle", "kill", "alert"]
ConstraintStatus = Literal["active", "paused", "archived"]

_LTE_ONLY_METRICS = frozenset({"cpc", "cpm", "cpcv", "fraud_rate"})
_GTE_ONLY_METRICS = frozenset({
    "vtr", "viewability", "roas", "revenue_per_day", "volume_per_day",
})
_RATE_METRICS = frozenset({"vtr", "viewability", "fraud_rate"})


def validate_metric_operator(metric: str, operator: str) -> None:
    if metric in _LTE_ONLY_METRICS and operator != "lte":
        raise ValueError(f"metric {metric} only allows operator lte")
    if metric in _GTE_ONLY_METRICS and operator != "gte":
        raise ValueError(f"metric {metric} only allows operator gte")


def validate_metric_value(metric: str, value: float) -> None:
    if value <= 0:
        raise ValueError("value must be positive")
    if metric in _RATE_METRICS and value > 1:
        raise ValueError(f"metric {metric} value must be <= 1")


class HardConstraintRead(ApiModel):
    id: str
    tenant_id: str
    optimization_strategy_id: str
    metric: ConstraintMetric
    operator: ConstraintOperator
    value: float
    violation_policy: ViolationPolicy
    status: ConstraintStatus

class HardConstraintCreate(ApiModel):
    metric: ConstraintMetric
    operator: ConstraintOperator
    value: float = Field(gt=0)
    violation_policy: ViolationPolicy = "freeze"
    status: ConstraintStatus = "active"

    @model_validator(mode="after")
    def check_metric_rules(self) -> HardConstraintCreate:
        validate_metric_operator(self.metric, self.operator)
        validate_metric_value(self.metric, self.value)
        return self


class HardConstraintUpdate(ApiModel):
    metric: ConstraintMetric | None = None
    operator: ConstraintOperator | None = None
    value: float | None = Field(default=None, gt=0)
    violation_policy: ViolationPolicy | None = None
    status: ConstraintStatus | None = None

    @model_validator(mode="after")
    def check_metric_rules(self) -> HardConstraintUpdate:
        metric = self.metric
        operator = self.operator
        value = self.value
        if metric is not None and operator is not None:
            validate_metric_operator(metric, operator)
        elif metric is not None and operator is None:
            raise ValueError("operator required when metric is updated")
        elif operator is not None and metric is None:
            raise ValueError("metric required when operator is updated")
        if value is not None and metric is not None:
            validate_metric_value(metric, value)
        return self
