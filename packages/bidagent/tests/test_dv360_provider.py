"""DV360 provider tests.

Goals of this suite:
1. The DV360 mock metrics provider produces canonical TermMetric rows
   the decision engine can consume without code changes.
2. Running the decision engine on DV360-shaped input yields a sensible
   Plan (at least one bid-up and one bid-down decision triggered).
3. The DV360 bid client's payload builder produces a body shape compatible
   with the DV360 bulkEdit endpoint.
4. The registry can resolve `dv360_mock`.
"""

from __future__ import annotations

from datetime import date

from bidagent.decision_engine import build_plan
from bidagent.models import ActionReason, HygieneRules, OptimizerConfig
from bidagent.providers import ProviderRegistry
from bidagent.providers.dv360 import (
    Dv360MockBidProvider,
    Dv360MockMetricsProvider,
    register_dv360_providers,
)
from bidagent.providers.dv360.bid_client import (
    build_bulk_edit_body,
    to_dv360_assigned_option,
)
from bidagent.providers.dv360.metrics_client import (
    DV360_DIMENSION_MAP,
    build_dimension_query_spec,
)


def _common_config() -> tuple[OptimizerConfig, HygieneRules]:
    cfg = OptimizerConfig(
        cpv_target=2.50,
        tolerance_band=0.20,
        max_modifier=2.0,
        max_step_per_run=0.40,
    )
    hygiene = HygieneRules(
        min_impressions_for_action=500,
        anomalous_ctr_threshold=0.04,
        min_viewability=0.40,
    )
    return cfg, hygiene


def _build_plan_via_dv360_mock():
    cfg, hygiene = _common_config()
    metrics_provider = Dv360MockMetricsProvider()
    bids_provider = Dv360MockBidProvider()

    metrics = metrics_provider.fetch_week_metrics(
        line_item_external_id="li-1234567890",
        week_start=date(2026, 5, 4),
        week_end=date(2026, 5, 10),
    )
    current_terms = bids_provider.get_current_modifiers("li-1234567890")
    current_mods = {
        (t.targeting_module, t.targeting_key, str(t.value)): t.modifier
        for t in current_terms
    }
    return build_plan(
        line_item_id=1234567890,
        line_item_name="Auto Brand IT — Display+Video (DV360)",
        week_label="2026-05-04 → 2026-05-10",
        metrics=metrics,
        current_modifiers=current_mods,
        runs_since_zeroed={},
        current_max_bid=4.50,
        cfg=cfg,
        hygiene=hygiene,
    )


def test_dv360_metrics_provider_returns_canonical_term_metrics():
    metrics = Dv360MockMetricsProvider().fetch_week_metrics(
        "any", date(2026, 5, 4), date(2026, 5, 10)
    )
    assert len(metrics) > 10, "expected a non-trivial week of metrics"
    # Coverage across our canonical dimension families
    modules = {m.targeting_module for m in metrics}
    assert {"inventory", "device", "geo", "audience"}.issubset(modules)
    # No spend-without-visits sanity break (TermMetric tolerates inf CPV)
    for m in metrics:
        assert m.impressions >= 0
        assert m.spend >= 0


def test_decision_engine_runs_on_dv360_input_unchanged():
    """The same decision engine code path works on
    DV360-shaped input without any conditional logic."""
    plan = _build_plan_via_dv360_mock()

    assert plan.line_item_id == 1234567890
    assert plan.blended_cpv_observed > 0
    assert plan.decisions, "engine should produce at least one decision"

    reasons = {d.reason for d in plan.decisions}
    # We expect a mix of bid-up / bid-down / on-target reasons given the
    # bias distribution baked into the DV360 mock.
    assert ActionReason.UNDER_TARGET in reasons, "no bid-up triggered"
    assert ActionReason.OVER_TARGET in reasons, "no bid-down triggered"


def test_dv360_to_assigned_option_handles_supported_terms():
    """Canonical → DV360 wire-shape mapping returns a dict for supported
    targeting types and None for unsupported ones."""
    from bidagent.models import ModifierTerm

    # Device (supported)
    t = ModifierTerm(
        targeting_module="device",
        targeting_key="device_type",
        value="MOBILE",
        modifier=1.25,
        field_label="Smartphone",
    )
    opt = to_dv360_assigned_option(t)
    assert opt is not None
    assert opt["targetingType"] == "TARGETING_TYPE_DEVICE_TYPE"
    # DV360 v4 uses per-type detail keys (deviceTypeDetails for device, etc.)
    details = opt["deviceTypeDetails"]
    assert details["bidMultiplier"] == 1.25
    assert details["targetingOptionId"] == "DEVICE_TYPE_SMART_PHONE"

    # Unsupported (random module)
    t2 = ModifierTerm(
        targeting_module="weather",
        targeting_key="condition",
        value="rain",
        modifier=0.8,
    )
    assert to_dv360_assigned_option(t2) is None


def test_bulk_edit_body_includes_changed_decisions_only():
    plan = _build_plan_via_dv360_mock()
    body = build_bulk_edit_body(plan)

    assert body["lineItemIds"] == [str(plan.line_item_id)]
    n_changed = len(plan.changed_decisions)

    # Each changed decision that maps to a DV360 targeting type produces
    # one create and one delete request entry.
    assert isinstance(body["createRequests"], list)
    assert isinstance(body["deleteRequests"], list)
    # The body must not exceed the number of changed decisions.
    assert len(body["createRequests"]) <= n_changed
    assert len(body["deleteRequests"]) <= n_changed


def test_dv360_apply_plan_dry_run_is_safe():
    plan = _build_plan_via_dv360_mock()
    result_dry = Dv360MockBidProvider().apply_plan(plan, dry_run=True)
    result_live = Dv360MockBidProvider().apply_plan(plan, dry_run=False)
    assert result_dry.ok and result_dry.dry_run
    # Mock providers stay safe even when caller requests live application.
    assert result_live.ok and result_live.dry_run


def test_query_spec_has_required_filters():
    spec = build_dimension_query_spec(
        advertiser_id="123",
        line_item_id="li-9",
        week_start=date(2026, 5, 4),
        week_end=date(2026, 5, 10),
    )
    filters = spec["params"]["filters"]
    types = {f["type"] for f in filters}
    assert "FILTER_ADVERTISER" in types
    assert "FILTER_LINE_ITEM" in types
    # The query must group by every canonical DV360 dimension we map.
    declared = set(spec["params"]["groupBys"])
    expected = set(DV360_DIMENSION_MAP.values())
    assert expected.issubset(declared)
    # The metadata must carry a structured CUSTOM_DATES range, not a string.
    data_range = spec["metadata"]["dataRange"]
    assert data_range["range"] == "CUSTOM_DATES"
    assert data_range["customStartDate"]["year"] == 2026
    assert data_range["customEndDate"]["day"] == 10


def test_registry_supports_dv360():
    reg = ProviderRegistry()
    register_dv360_providers(reg)

    available = reg.available()
    assert "dv360_mock" in available

    d_metrics, d_bids = reg.build("dv360_mock")
    assert d_metrics.__class__.__name__ == "Dv360MockMetricsProvider"
    assert d_bids.__class__.__name__ == "Dv360MockBidProvider"
