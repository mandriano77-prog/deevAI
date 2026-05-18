"""Deterministic DV360-shaped mock data for tests and demos.

DV360-flavoured synthetic metrics:
- inventory domains stay similar (URL-shaped strings),
- device.device_type values use DV360 tokens,
- geo dimensions cover country/region/city,
- audience.id uses Google audience-list IDs.

The numerical shape (impressions / clicks / visits / spend) is chosen to
trigger the same mix of OVER_TARGET / UNDER_TARGET / ON_TARGET decisions
that the DV360 engine should trigger — useful when sanity-checking that the
decision engine treats both providers symmetrically.
"""

from __future__ import annotations

import random
from typing import Iterable

from ...models import TermMetric


def _metric(
    module: str,
    key: str,
    value: str,
    label: str,
    impressions: int,
    clicks: int,
    visits: int,
    spend: float,
) -> TermMetric:
    return TermMetric(
        targeting_module=module,
        targeting_key=key,
        value=value,
        field_label=label,
        impressions=impressions,
        clicks=clicks,
        visits=visits,
        spend=spend,
    )


def fake_dv360_week_metrics(seed: int = 7) -> list[TermMetric]:
    """Deterministic week of metrics shaped like DV360 reporting output."""
    rng = random.Random(seed)

    inventory = [
        ("inventory", "domain", "lastampa.it", "lastampa.it"),
        ("inventory", "domain", "corriere.it", "corriere.it"),
        ("inventory", "domain", "ilmessaggero.it", "ilmessaggero.it"),
        ("inventory", "domain", "repubblica.it", "repubblica.it"),
        ("inventory", "app", "com.spotify.music", "Spotify (Android)"),
        ("inventory", "app", "com.google.android.youtube", "YouTube (Android)"),
    ]
    devices = [
        ("device", "device_type", "DESKTOP", "Desktop"),
        ("device", "device_type", "MOBILE", "Smartphone"),
        ("device", "device_type", "TABLET", "Tablet"),
        ("device", "device_type", "CTV", "Connected TV"),
    ]
    geos = [
        ("geo", "country", "IT", "Italia"),
        ("geo", "region", "IT-25", "Lombardia"),
        ("geo", "region", "IT-62", "Lazio"),
        ("geo", "city", "milan", "Milano"),
        ("geo", "city", "roma", "Roma"),
        ("geo", "city", "torino", "Torino"),
    ]
    audiences = [
        ("audience", "id", "9001", "Auto Intenders 30d"),
        ("audience", "id", "9002", "Banking & Finance Affinity"),
        ("audience", "id", "9003", "Travel — Premium"),
    ]

    out: list[TermMetric] = []

    # 1) Inventory: a couple of cheap performers, a couple of expensive ones
    for i, (mod, key, val, label) in enumerate(inventory):
        impressions = rng.randint(20_000, 250_000)
        ctr = 0.005 + rng.random() * 0.02
        clicks = int(impressions * ctr)
        visit_rate = 0.30 + rng.random() * 0.40  # 30-70% of clicks become visits
        visits = int(clicks * visit_rate)
        # Bias spend to make some terms way under / over target (~2.50 CPV)
        bias = [0.6, 0.9, 1.4, 2.2, 1.0, 1.1][i]
        spend = visits * 2.50 * bias if visits else 0
        out.append(_metric(mod, key, val, label, impressions, clicks, visits, spend))

    # 2) Devices: CTV is expensive, MOBILE is on target, DESKTOP is cheap
    biases = {"DESKTOP": 0.7, "MOBILE": 1.0, "TABLET": 1.3, "CTV": 2.4}
    for mod, key, val, label in devices:
        impressions = rng.randint(50_000, 300_000)
        clicks = int(impressions * (0.006 + rng.random() * 0.012))
        visits = int(clicks * (0.35 + rng.random() * 0.25))
        spend = visits * 2.50 * biases[val] if visits else 0
        out.append(_metric(mod, key, val, label, impressions, clicks, visits, spend))

    # 3) Geo: one country on target, regions/cities mixed
    geo_biases = [1.0, 0.85, 1.15, 0.8, 1.6, 1.05]
    for (mod, key, val, label), bias in zip(geos, geo_biases):
        impressions = rng.randint(15_000, 200_000)
        clicks = int(impressions * (0.007 + rng.random() * 0.015))
        visits = int(clicks * (0.35 + rng.random() * 0.30))
        spend = visits * 2.50 * bias if visits else 0
        out.append(_metric(mod, key, val, label, impressions, clicks, visits, spend))

    # 4) Audiences: include one anomalous low-volume term (gets gated out)
    aud_biases = [0.7, 1.1, 1.8]
    for (mod, key, val, label), bias in zip(audiences, aud_biases):
        impressions = rng.randint(8_000, 60_000)
        clicks = int(impressions * (0.005 + rng.random() * 0.010))
        visits = int(clicks * (0.25 + rng.random() * 0.30))
        spend = visits * 2.50 * bias if visits else 0
        out.append(_metric(mod, key, val, label, impressions, clicks, visits, spend))

    return out


def filter_supported_metrics(metrics: list[TermMetric]) -> list[TermMetric]:
    """No-op for DV360 — every targeting dimension we emit is supported
    by the DV360 bid_strategy API. Kept as a function so the call sites
    (scheduler, runtime) read uniformly and
    we can add filtering later without touching them.
    """
    return list(metrics)


def fake_current_bid_multipliers(
    metrics: Iterable[TermMetric],
) -> dict[tuple[str, str, str], float]:
    """All terms start at neutral multiplier 1.0 (matches DV360 default)."""
    return {(m.targeting_module, m.targeting_key, str(m.value)): 1.0 for m in metrics}


def fake_runs_since_zeroed() -> dict[tuple[str, str, str], int]:
    """No previously-zeroed terms in this scenario."""
    return {}
