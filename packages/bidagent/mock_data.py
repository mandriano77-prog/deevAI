"""Mock data generator: simulates one week of Antenna output.

Lets us run the full pipeline end-to-end without a Beeswax account.
Once Antenna is connected the shape stays the same — we swap the
function, not the contract."""

from __future__ import annotations

import random
from typing import Optional

from .models import TermMetric


def _metric(
    module: str,
    key: str,
    value: str,
    label: str,
    impressions: int,
    visit_rate: float,
    cpc: float,
    ctr: float = 0.005,
    viewability: float = 0.65,
) -> TermMetric:
    """Helper that derives clicks/visits/spend from clean parameters."""
    clicks = int(impressions * ctr)
    visits = int(clicks * visit_rate)
    spend = clicks * cpc
    viewable = int(impressions * viewability)
    return TermMetric(
        targeting_module=module,
        targeting_key=key,
        value=value,
        field_label=label,
        impressions=impressions,
        clicks=clicks,
        visits=visits,
        spend=round(spend, 2),
        viewable_impressions=viewable,
    )


def fake_week_metrics(seed: int = 42) -> list[TermMetric]:
    """A realistic-ish week of CPV data for one Line Item.

    Patterns we deliberately bake in (so the engine has interesting
    decisions to make):
      - Daypart 18-22 weekday: cheap, lots of visits (under target)
      - Daypart 00-06: lots of impressions, zero visits (over target)
      - Safari: solid mid performer (on target)
      - Chrome: above target
      - One bad publisher: anomalously high CTR (will be zeroed)
      - One niche geo: too few impressions (volume gate)
    """
    random.seed(seed)
    metrics: list[TermMetric] = []

    # --- Daypart × weekday ---
    # Mon-Fri 18:00-22:00: high engagement window
    metrics.append(_metric(
        module="time", key="daypart_weekday",
        value="MON_FRI_1800_2200", label="Lun-Ven 18-22",
        impressions=240_000, visit_rate=0.42, cpc=0.18, ctr=0.0065,
        viewability=0.78,
    ))
    # Mon-Fri 09:00-12:00: average
    metrics.append(_metric(
        module="time", key="daypart_weekday",
        value="MON_FRI_0900_1200", label="Lun-Ven 9-12",
        impressions=180_000, visit_rate=0.30, cpc=0.22, ctr=0.0050,
        viewability=0.70,
    ))
    # Night 00-06: lots of impressions, almost no visits (bots/idle)
    metrics.append(_metric(
        module="time", key="daypart_weekday",
        value="ALL_0000_0600", label="Notte 00-06",
        impressions=160_000, visit_rate=0.04, cpc=0.10, ctr=0.0030,
        viewability=0.45,
    ))
    # Weekend afternoon
    metrics.append(_metric(
        module="time", key="daypart_weekday",
        value="SAT_SUN_1400_1800", label="Weekend 14-18",
        impressions=130_000, visit_rate=0.35, cpc=0.20, ctr=0.0058,
        viewability=0.72,
    ))

    # --- Browser ---
    metrics.append(_metric(
        module="platform", key="browser",
        value="Safari", label="Safari",
        impressions=210_000, visit_rate=0.38, cpc=0.21, ctr=0.0061,
        viewability=0.74,
    ))
    metrics.append(_metric(
        module="platform", key="browser",
        value="Chrome", label="Chrome",
        impressions=380_000, visit_rate=0.22, cpc=0.25, ctr=0.0048,
        viewability=0.68,
    ))
    metrics.append(_metric(
        module="platform", key="browser",
        value="Firefox", label="Firefox",
        impressions=42_000, visit_rate=0.31, cpc=0.19, ctr=0.0052,
        viewability=0.71,
    ))

    # --- Device ---
    metrics.append(_metric(
        module="device", key="device_type",
        value="MOBILE", label="Mobile",
        impressions=420_000, visit_rate=0.29, cpc=0.23, ctr=0.0058,
        viewability=0.66,
    ))
    metrics.append(_metric(
        module="device", key="device_type",
        value="DESKTOP", label="Desktop",
        impressions=190_000, visit_rate=0.41, cpc=0.20, ctr=0.0054,
        viewability=0.79,
    ))

    # --- Geo (Italian regions) ---
    metrics.append(_metric(
        module="geo", key="region",
        value="IT-25", label="Lombardia",
        impressions=180_000, visit_rate=0.36, cpc=0.22, ctr=0.0061,
        viewability=0.73,
    ))
    metrics.append(_metric(
        module="geo", key="region",
        value="IT-62", label="Lazio",
        impressions=110_000, visit_rate=0.33, cpc=0.21, ctr=0.0055,
        viewability=0.71,
    ))
    # A niche geo with too few impressions: volume gate
    metrics.append(_metric(
        module="geo", key="region",
        value="IT-77", label="Basilicata",
        impressions=320, visit_rate=0.30, cpc=0.18, ctr=0.0050,
        viewability=0.70,
    ))

    # --- Publisher (one bad apple) ---
    metrics.append(_metric(
        module="inventory", key="domain",
        value="clickfarm-example.tld", label="clickfarm-example.tld",
        impressions=85_000, visit_rate=0.02, cpc=0.05, ctr=0.052,
        viewability=0.30,
    ))
    metrics.append(_metric(
        module="inventory", key="domain",
        value="repubblica.it", label="repubblica.it",
        impressions=72_000, visit_rate=0.39, cpc=0.28, ctr=0.0066,
        viewability=0.81,
    ))

    return metrics


def fake_current_modifiers(metrics: list[TermMetric]) -> dict[tuple[str, str, str], float]:
    """Returns a baseline of modifiers (mostly 1.0) so we can see deltas.

    A couple of pre-existing non-1.0 values to show smoothing in action."""
    base: dict[tuple[str, str, str], float] = {}
    for m in metrics:
        key = (m.targeting_module, m.targeting_key, str(m.value))
        base[key] = 1.0
    # Pretend last week we already boosted Safari and cut Chrome
    safari_key = ("platform", "browser", "Safari")
    chrome_key = ("platform", "browser", "Chrome")
    if safari_key in base:
        base[safari_key] = 1.20
    if chrome_key in base:
        base[chrome_key] = 0.90
    return base


def fake_runs_since_zeroed() -> dict[tuple[str, str, str], int]:
    """Simulate one term that was zeroed 4 runs ago → ready to revive."""
    return {
        ("inventory", "domain", "old-blocked-site.tld"): 5,
    }


def fake_action_metrics(
    seed: int = 42,
) -> tuple[list["ActionMetric"], dict[tuple[str, str, str], list["ActionMetric"]]]:
    """Synthetic multi-action counts for blended CPA / ROAS demos.

    Returns (catalog, per_term_map) where each term inherits the same
    funnel action counts until AMC exposes term-level attribution.
    """
    from .models import ActionMetric

    rng = random.Random(seed)
    catalog = [
        ActionMetric("visita_listing", weight=1.0, value_eur=1.0, count=rng.randint(8, 20)),
        ActionMetric("richiesta_info", weight=8.0, value_eur=7.0, count=rng.randint(2, 8)),
        ActionMetric("appuntamento", weight=30.0, value_eur=50.0, count=rng.randint(1, 4)),
    ]
    metrics = fake_week_metrics(seed=seed)
    by_term: dict[tuple[str, str, str], list[ActionMetric]] = {}
    for m in metrics:
        key = (m.targeting_module, m.targeting_key, str(m.value))
        by_term[key] = catalog
    return catalog, by_term
