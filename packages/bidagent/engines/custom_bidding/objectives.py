"""Canonical objectives for deevAI Custom Bidding.

The product surface is **three sliders**: Performance, Quality, Reach.
Each slider is a weight ∈ [0, 1]. The three weights sum to 1.0.

Internally, each objective expands into a *recipe* — a small set of
criteria (DV360 DSL conditions) + scores that get fed into a
`sum_aggregate(...)` call in the generated script.

A recipe is intentionally narrow: not "all possible signals related to
performance", but a *curated, opinionated default* that maps cleanly to
what an advertiser typically wants. Specialists can override per tenant
via `recipe_overrides`, but the defaults below ship out of the box.

Glossary
- **Criterion**: a list of DSL conditions ANDed together.
- **Weight**: numeric score awarded when all conditions are true.
- **Recipe**: list of (criterion, weight) pairs that defines an objective.

The score range is conventionally 0..1000 — DV360 sorts impressions by
this score; absolute values don't matter, only relative ordering. We
keep everything in single-digit weights and scale by the slider at
generation time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class ObjectiveId(str, Enum):
    """The three canonical objectives shown in the deevAI UI sliders."""

    PERFORMANCE = "performance"
    QUALITY = "quality"
    REACH = "reach"


@dataclass(frozen=True)
class Criterion:
    """One AND-joined condition with its raw DSL form.

    We store the DSL source directly so the generator can dump it
    verbatim. The validator parses these strings later to confirm they
    only reference allowed signals.

    `weight` is the score awarded when the criterion is true. It will
    be multiplied by the objective's slider weight before emission.

    `comment` is an optional human note rendered above the criterion in
    the generated script (great for client trust).
    """

    expression: str
    weight: float
    comment: str = ""


@dataclass(frozen=True)
class Recipe:
    """The DSL-level expansion of one objective for a given tenant config."""

    objective: ObjectiveId
    criteria: tuple[Criterion, ...]
    # Optional: signals the recipe needs that aren't standard (e.g. a
    # tenant-specific Floodlight Activity ID for conversions). Captured
    # so the script generator can render them with the right IDs.
    requires_floodlight_activity_id: int | None = None
    requires_attribution_model_id: int = 0  # 0 = last-touch default


@dataclass(frozen=True)
class TenantConfig:
    """Inputs the engine needs from the tenant to expand objectives.

    `weights` must sum to ~1.0 (we tolerate ±0.001). All three keys must
    be present; passing 0 for an objective excludes it from the script.

    `floodlight_activity_id` is required iff `weights.performance > 0`.

    `country_focus` (optional) lets us prefer impressions matching a
    short ISO country list (e.g. ["IT"]) — useful for IT-only campaigns.
    """

    weights: dict[ObjectiveId, float]
    floodlight_activity_id: int | None = None
    attribution_model_id: int = 0
    country_focus: tuple[str, ...] = ()
    # Operational hours considered "prime time" for the brand. Defaults
    # cover Italian e-commerce daytime (9-22 local). Empty disables.
    prime_hours: tuple[int, ...] = tuple(range(9, 23))


# ──────────────────────────────────────────────────────────────────── helpers


def _format_int_list(values: Iterable[int]) -> str:
    return "[" + ", ".join(str(v) for v in values) + "]"


def _format_str_list(values: Iterable[str]) -> str:
    quoted = ", ".join(f'"{v}"' for v in values)
    return f"[{quoted}]"


# ───────────────────────────────────────────────────────────── recipe builders


def build_performance_recipe(cfg: TenantConfig) -> Recipe:
    """Performance recipe — values impressions that *actually convert*.

    The hierarchy is:
      1. Impression that drove a conversion with positive revenue → very
         high weight, scaled by the revenue value itself.
      2. Impression that drove a conversion without revenue → medium.
      3. Impression that drove a click → small (proxy when no conv).
    """
    if cfg.floodlight_activity_id is None:
        raise ValueError(
            "Performance objective requires a Floodlight Activity ID. "
            "Set TenantConfig.floodlight_activity_id."
        )

    activity = cfg.floodlight_activity_id
    model = cfg.attribution_model_id

    # In the DV360 DSL we use the conversion callables as criteria. Each
    # callable returns a Double > 0 if there was attribution; truthy in
    # the criteria array means "non-zero".
    criteria = (
        Criterion(
            expression=f"total_conversion_value({activity}, {model}) > 0",
            weight=700.0,
            comment="Converted with revenue — primary success signal",
        ),
        Criterion(
            expression=f"total_conversion_count({activity}, {model}) > 0",
            weight=400.0,
            comment="Converted without revenue (lead, signup, etc.)",
        ),
        Criterion(
            expression="click == 1",
            weight=50.0,
            comment="Clicked — weak signal but better than nothing",
        ),
    )
    return Recipe(
        objective=ObjectiveId.PERFORMANCE,
        criteria=criteria,
        requires_floodlight_activity_id=activity,
        requires_attribution_model_id=model,
    )


def build_quality_recipe(cfg: TenantConfig) -> Recipe:
    """Quality recipe — values *attention* over volume.

    We reward:
      1. Active View viewed (Google's MRC viewable standard).
      2. Time-on-screen ≥ 5s (proxy for genuine attention).
      3. Above-the-fold placement.
      4. Video completed (when applicable — non-video impressions naturally
         have this as 0 / falsy so they get 0 weight here, which is correct).
    """
    criteria = (
        Criterion(
            expression="active_view_viewed == 1",
            weight=400.0,
            comment="MRC-viewable impression",
        ),
        Criterion(
            expression="time_on_screen_seconds >= 5",
            weight=200.0,
            comment="≥5s on screen — sustained attention",
        ),
        Criterion(
            expression="ad_position == 1",
            weight=200.0,
            comment="Above-the-fold placement",
        ),
        Criterion(
            expression="video_completed == 1",
            weight=200.0,
            comment="Video VTR — only applies to video creatives",
        ),
    )
    return Recipe(objective=ObjectiveId.QUALITY, criteria=criteria)


def build_reach_recipe(cfg: TenantConfig) -> Recipe:
    """Reach recipe — values *prime-time, in-market reach*.

    The reach objective is opinionated about *when* and *where* you
    spend, not just maximising impression count.

    We reward:
      1. Impressions in the configured prime_hours.
      2. Impressions in the country_focus list (if any).
      3. Smart-phone or connected-TV environment (mass-reach devices).
    """
    criteria: list[Criterion] = []

    if cfg.prime_hours:
        hours_list = _format_int_list(cfg.prime_hours)
        criteria.append(
            Criterion(
                expression=f"hour_of_day in {hours_list}",
                weight=300.0,
                comment=f"Within prime hours {min(cfg.prime_hours)}-{max(cfg.prime_hours)}",
            )
        )

    if cfg.country_focus:
        countries = _format_str_list(cfg.country_focus)
        criteria.append(
            Criterion(
                expression=f"country_code in {countries}",
                weight=300.0,
                comment=f"In-market: {', '.join(cfg.country_focus)}",
            )
        )

    # Mass-reach devices: smartphone (2) + connected_tv (5).
    criteria.append(
        Criterion(
            expression="device_type in [2, 5]",
            weight=200.0,
            comment="Mass-reach device (smartphone or connected TV)",
        )
    )

    return Recipe(objective=ObjectiveId.REACH, criteria=tuple(criteria))


OBJECTIVE_BUILDERS: dict[ObjectiveId, callable] = {
    ObjectiveId.PERFORMANCE: build_performance_recipe,
    ObjectiveId.QUALITY: build_quality_recipe,
    ObjectiveId.REACH: build_reach_recipe,
}


# ───────────────────────────────────────────────────────────────────── facade


def validate_weights(weights: dict[ObjectiveId, float]) -> None:
    """Validate the slider tuple.

    Rules:
      - All three keys present.
      - Each weight in [0, 1].
      - Sum ≈ 1.0 (±0.001 tolerance for floating-point UI rounding).
    """
    required = {ObjectiveId.PERFORMANCE, ObjectiveId.QUALITY, ObjectiveId.REACH}
    missing = required - weights.keys()
    if missing:
        raise ValueError(f"Missing objective weights for: {sorted(m.value for m in missing)}")

    for obj, w in weights.items():
        if not (0.0 <= w <= 1.0):
            raise ValueError(
                f"Weight for {obj.value} = {w} is out of range [0, 1]"
            )

    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise ValueError(
            f"Objective weights must sum to 1.0 (±0.001); got {total:.4f}"
        )


def expand_objectives(cfg: TenantConfig) -> list[tuple[Recipe, float]]:
    """Expand the active objectives into (recipe, weight) pairs.

    Objectives with weight=0 are skipped entirely (no criteria emitted).
    Returns the recipes in stable order: Performance, Quality, Reach.
    """
    validate_weights(cfg.weights)
    result: list[tuple[Recipe, float]] = []
    for obj_id in (ObjectiveId.PERFORMANCE, ObjectiveId.QUALITY, ObjectiveId.REACH):
        w = cfg.weights.get(obj_id, 0.0)
        if w <= 0.0:
            continue
        recipe = OBJECTIVE_BUILDERS[obj_id](cfg)
        result.append((recipe, w))
    return result
