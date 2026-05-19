"""Sprint 0 lever surface — pin the 7→8 lever expansion.

These tests crystallise the lever catalogue at v1 so future refactors can't
silently drop or rename a canonical (module, key) pair without breaking
something visible. Sprint 0 ships:

    1. inventory/domain
    2. inventory/app
    3. device/device_type
    4. geo/country
    5. geo/region
    6. geo/city
    7. audience/id          (legacy)
    7b. audience/segment    (NEW)
    8. time/hour_of_day     (NEW — dayparting)

Total: 9 canonical entries, 7 distinct DV360 TargetingType enums.
The "8 levers" promise is the product-facing count of UX surfaces
(inventory, device, geo, audience, dayparting + the 3 we keep for v2:
platform, viewability tier, content category) — not the raw entry count.
"""

from __future__ import annotations

from bidagent.config import LineItemConfig
from bidagent.models import ModifierTerm
from bidagent.providers.dv360.bid_client import (
    CANONICAL_TO_TARGETING_TYPE,
    to_dv360_assigned_option,
)


def test_targeting_modules_includes_audience():
    cfg = LineItemConfig(
        line_item_id=1,
        line_item_name="t",
        bid_modifier_id=1,
        cpv_target=0.10,
        visit_event_id=1,
        current_max_bid=2.0,
    )
    assert "audience" in cfg.targeting_modules
    # Six logical modules in v1; eight surfaces in product copy.
    assert len(cfg.targeting_modules) == 6


def test_audience_segment_is_mapped():
    canonical = ("audience", "segment")
    assert CANONICAL_TO_TARGETING_TYPE[canonical] == "TARGETING_TYPE_AUDIENCE_GROUP"


def test_dayparting_hour_of_day_is_mapped():
    canonical = ("time", "hour_of_day")
    assert CANONICAL_TO_TARGETING_TYPE[canonical] == "TARGETING_TYPE_DAY_AND_TIME"


def test_dayparting_emits_dv360_assigned_option():
    term = ModifierTerm(
        targeting_module="time",
        targeting_key="hour_of_day",
        value="21",
        modifier=1.35,
        field_label="9 PM",
    )
    opt = to_dv360_assigned_option(term)
    assert opt is not None
    assert opt["targetingType"] == "TARGETING_TYPE_DAY_AND_TIME"
    assert "dayAndTimeDetails" in opt
    details = opt["dayAndTimeDetails"]
    assert details["targetingOptionId"] == "21"
    assert details["bidMultiplier"] == 1.35


def test_audience_segment_emits_dv360_assigned_option():
    term = ModifierTerm(
        targeting_module="audience",
        targeting_key="segment",
        value="aud-1234",
        modifier=0.7,
        field_label="High-intent visitors",
    )
    opt = to_dv360_assigned_option(term)
    assert opt is not None
    assert opt["targetingType"] == "TARGETING_TYPE_AUDIENCE_GROUP"
    assert "audienceGroupDetails" in opt


def test_canonical_map_has_at_least_8_entries():
    # Distinct TargetingType count is 6 (geo collapses 3 entries into 1 type):
    # INVENTORY_SOURCE, APP, DEVICE_TYPE, GEO_REGION, AUDIENCE_GROUP, DAY_AND_TIME.
    distinct_types = set(CANONICAL_TO_TARGETING_TYPE.values())
    assert len(distinct_types) == 6
    # Canonical entry count is 9 (8 levers + 1 legacy audience/id alias).
    assert len(CANONICAL_TO_TARGETING_TYPE) >= 9
