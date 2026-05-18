"""Pydantic schemas for metric-agnostic OptimizationStrategy."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from ..services.metrics import ALLOWED_METRICS
from .base import ApiModel

StrategyMode = Literal["single", "blended_2", "blended_3"]
ObjectiveMetric = Literal[
    "cpv", "cpc", "cpcv", "cpm", "cpa", "roas", "custom_action",
]
StrategyStatus = Literal["active", "paused", "archived"]

_WEIGHT_SUM_TOLERANCE = 0.01


def _weights_sum(*weights: float | None) -> float:
    return sum(w for w in weights if w is not None)


class OptimizationStrategyRead(ApiModel):
    id: str
    tenant_id: str
    line_item_id: str | None
    mode: StrategyMode
    primary_metric: ObjectiveMetric
    primary_target: float
    primary_weight: float
    secondary_metric: ObjectiveMetric | None
    secondary_target: float | None
    secondary_weight: float | None
    tertiary_metric: ObjectiveMetric | None
    tertiary_target: float | None
    tertiary_weight: float | None
    primary_action_id: str | None
    tolerance_band: float
    status: StrategyStatus


class _StrategyBodyBase(ApiModel):
    line_item_id: str | None = None
    mode: StrategyMode = "single"
    primary_metric: ObjectiveMetric = "cpv"
    primary_target: float = Field(gt=0)
    primary_weight: float = Field(default=100.0, ge=0, le=100)
    secondary_metric: ObjectiveMetric | None = None
    secondary_target: float | None = Field(default=None, gt=0)
    secondary_weight: float | None = Field(default=None, ge=0, le=100)
    tertiary_metric: ObjectiveMetric | None = None
    tertiary_target: float | None = Field(default=None, gt=0)
    tertiary_weight: float | None = Field(default=None, ge=0, le=100)
    primary_action_id: str | None = None
    tolerance_band: float = Field(default=0.20, gt=0, le=0.5)
    status: StrategyStatus = "active"

    @model_validator(mode="after")
    def validate_mode_and_weights(self) -> Self:
        if self.primary_metric not in ALLOWED_METRICS:
            raise ValueError(f"Invalid primary_metric: {self.primary_metric}")

        if self.mode == "single":
            if self.primary_weight != 100:
                raise ValueError("mode=single requires primary_weight=100")
            if any(
                v is not None
                for v in (
                    self.secondary_metric,
                    self.secondary_target,
                    self.secondary_weight,
                    self.tertiary_metric,
                    self.tertiary_target,
                    self.tertiary_weight,
                )
            ):
                raise ValueError("mode=single must not include secondary/tertiary fields")
        elif self.mode == "blended_2":
            if self.secondary_metric is None or self.secondary_target is None:
                raise ValueError("mode=blended_2 requires secondary_metric and secondary_target")
            if self.secondary_weight is None:
                raise ValueError("mode=blended_2 requires secondary_weight")
            if any(v is not None for v in (self.tertiary_metric, self.tertiary_target, self.tertiary_weight)):
                raise ValueError("mode=blended_2 must not include tertiary fields")
            total = _weights_sum(self.primary_weight, self.secondary_weight)
            if abs(total - 100) > _WEIGHT_SUM_TOLERANCE:
                raise ValueError(f"blended_2 weights must sum to 100 (got {total})")
        elif self.mode == "blended_3":
            if any(
                v is None
                for v in (
                    self.secondary_metric,
                    self.secondary_target,
                    self.secondary_weight,
                    self.tertiary_metric,
                    self.tertiary_target,
                    self.tertiary_weight,
                )
            ):
                raise ValueError("mode=blended_3 requires all secondary and tertiary fields")
            total = _weights_sum(
                self.primary_weight, self.secondary_weight, self.tertiary_weight,
            )
            if abs(total - 100) > _WEIGHT_SUM_TOLERANCE:
                raise ValueError(f"blended_3 weights must sum to 100 (got {total})")

        if self.primary_metric == "custom_action" and not self.primary_action_id:
            raise ValueError("primary_action_id required when primary_metric=custom_action")

        return self


class OptimizationStrategyCreate(_StrategyBodyBase):
    pass


class OptimizationStrategyUpdate(ApiModel):
    mode: StrategyMode | None = None
    primary_metric: ObjectiveMetric | None = None
    primary_target: float | None = Field(default=None, gt=0)
    primary_weight: float | None = Field(default=None, ge=0, le=100)
    secondary_metric: ObjectiveMetric | None = None
    secondary_target: float | None = Field(default=None, gt=0)
    secondary_weight: float | None = Field(default=None, ge=0, le=100)
    tertiary_metric: ObjectiveMetric | None = None
    tertiary_target: float | None = Field(default=None, gt=0)
    tertiary_weight: float | None = Field(default=None, ge=0, le=100)
    primary_action_id: str | None = None
    tolerance_band: float | None = Field(default=None, gt=0, le=0.5)
    status: StrategyStatus | None = None

    @model_validator(mode="after")
    def validate_partial_update(self) -> Self:
        if self.tolerance_band is not None and not (0 < self.tolerance_band <= 0.5):
            raise ValueError("tolerance_band must be in (0, 0.5]")
        return self
