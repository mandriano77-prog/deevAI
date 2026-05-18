"""Catalog of the signals (variables) and functions DV360 exposes inside
custom-bidding scoring scripts.

Source: https://support.google.com/displayvideo/answer/11967043?hl=en

Custom-bidding scripts are NOT Python. They are a Google-proprietary DSL
that *looks* like Python but only supports:

- a handful of built-in *signals* (variables) injected per impression
- 3 aggregate functions (`first_match_aggregate`, `max_aggregate`,
  `sum_aggregate`)
- 4 casting functions (`bool`, `float`, `int`, `str`)
- 1 math function (`log`)
- arithmetic / comparison / membership operators
- `return <expr>` and `return None`
- comments (`#`, `'''`, `\"\"\"`)

NO `import`, NO function definitions, NO loops, NO assignment to globals,
NO list/dict comprehensions, NO classes, NO try/except, NO I/O.

Per script you write exactly one `return` (or branched returns) whose
final value is the impression's score (a `Double`). `return None`
excludes the impression from training.

This module is the single source of truth: every other piece of the
custom-bidding engine (generator, validator, UI) must consult it to
know what's allowed. Adding a signal here = adding it everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


# ────────────────────────────────────────────────────────────────────── enums


class SignalType(str, Enum):
    """Output type of a signal — matches DV360's type names verbatim."""

    BOOLEAN = "boolean"
    BINARY = "binary"
    DOUBLE = "double"
    INTEGER = "integer"
    STRING = "string"
    LIST_OF_INTEGERS = "list_of_integers"


class SignalCategory(str, Enum):
    """Groupings used by the doc — kept identical so the UI can render
    "signal picker" sections the same way DV360 does."""

    GENERAL = "general"
    DATE_TIME = "date_time"
    LOCATION = "location"
    CREATIVE = "creative"
    COMPUTER_SYSTEM = "computer_system"
    SERVING = "serving"
    ACTIVE_VIEW = "active_view"
    EVENT = "event"
    VIDEO = "video"
    CONVERSION = "conversion"
    GOOGLE_ANALYTICS = "google_analytics"


# ──────────────────────────────────────────────────────────────────── records


@dataclass(frozen=True)
class Signal:
    """A single DV360 custom-bidding signal."""

    name: str
    type: SignalType
    category: SignalCategory
    description: str
    # If True, this signal is a *callable* (e.g. ``total_conversion_value(activity_id, model_id)``)
    # rather than a bare variable.
    is_callable: bool = False
    # Required-argument names for callables (in order). Empty for variables.
    arg_names: tuple[str, ...] = ()
    # Optional enum-like value map: { value → human label }. Used by the UI.
    value_map: dict[int, str] | None = None
    # Deprecation marker — Q3 2025 ID-space migration replaced *_id with
    # *_reportable_id for several signals. We keep the old names out of
    # the catalog and only expose the new ones.
    deprecated: bool = False


@dataclass(frozen=True)
class BuiltinFunction:
    """A callable function the DSL allows."""

    name: str
    return_type: SignalType
    description: str
    # ("name", "type") pairs, in argument order.
    params: tuple[tuple[str, str], ...] = ()


# ─────────────────────────────────────────────────────────────────────── signals
# Order inside each category mirrors the official doc top-to-bottom so a
# human reading the catalog can cross-reference quickly.


SIGNALS: Final[tuple[Signal, ...]] = (
    # ─────── General ───────
    Signal(
        "advertiser_id",
        SignalType.INTEGER,
        SignalCategory.GENERAL,
        "DV360 advertiser identifier.",
    ),
    Signal(
        "insertion_order_id",
        SignalType.INTEGER,
        SignalCategory.GENERAL,
        "DV360 insertion order identifier.",
    ),
    Signal(
        "line_item_id",
        SignalType.INTEGER,
        SignalCategory.GENERAL,
        "DV360 line item identifier.",
    ),
    # ─────── Date / Time ───────
    Signal(
        "date",
        SignalType.INTEGER,
        SignalCategory.DATE_TIME,
        "Impression date (local), format yyyymmdd.",
    ),
    Signal(
        "day_of_week",
        SignalType.INTEGER,
        SignalCategory.DATE_TIME,
        "0=Sunday … 6=Saturday (browser-local).",
        value_map={
            0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed",
            4: "Thu", 5: "Fri", 6: "Sat",
        },
    ),
    Signal(
        "hour_of_day",
        SignalType.INTEGER,
        SignalCategory.DATE_TIME,
        "Hour 0-23 (browser-local).",
    ),
    Signal(
        "utc_date",
        SignalType.INTEGER,
        SignalCategory.DATE_TIME,
        "Impression date (UTC), format yyyymmdd.",
    ),
    Signal(
        "utc_hour_of_day",
        SignalType.INTEGER,
        SignalCategory.DATE_TIME,
        "Hour 0-23 (UTC).",
    ),
    # ─────── Location ───────
    Signal(
        "city_id",
        SignalType.INTEGER,
        SignalCategory.LOCATION,
        "DV360 city ID. Lookup via API or SDF metadata.",
    ),
    Signal(
        "country_code",
        SignalType.STRING,
        SignalCategory.LOCATION,
        'ISO-like country/region code, e.g. "IT", "US".',
    ),
    Signal(
        "country_id",
        SignalType.INTEGER,
        SignalCategory.LOCATION,
        "DV360 country ID.",
    ),
    Signal(
        "dma_id",
        SignalType.INTEGER,
        SignalCategory.LOCATION,
        "Designated market area identifier.",
    ),
    Signal(
        "zip_postal_code",
        SignalType.STRING,
        SignalCategory.LOCATION,
        "ZIP / postal code as a string.",
    ),
    # ─────── Creative (General) ───────
    Signal(
        "ad_type",
        SignalType.INTEGER,
        SignalCategory.CREATIVE,
        "0=display, 1=video, 2=audio.",
        value_map={0: "display", 1: "video", 2: "audio"},
    ),
    Signal(
        "creative_height",
        SignalType.INTEGER,
        SignalCategory.CREATIVE,
        "Creative height in pixels (display only).",
    ),
    Signal(
        "creative_id",
        SignalType.INTEGER,
        SignalCategory.CREATIVE,
        "Creative ID as shown in DV360.",
    ),
    Signal(
        "creative_width",
        SignalType.INTEGER,
        SignalCategory.CREATIVE,
        "Creative width in pixels (display only).",
    ),
    # ─────── Computer System ───────
    Signal(
        "browser_reportable_id",
        SignalType.INTEGER,
        SignalCategory.COMPUTER_SYSTEM,
        "Browser ID (Q3 2025 reportable_id ID space).",
    ),
    Signal(
        "browser_timezone_offset_minutes",
        SignalType.INTEGER,
        SignalCategory.COMPUTER_SYSTEM,
        "Minutes between browser TZ and GMT-12 (e.g. 1320 = GMT+10).",
    ),
    Signal(
        "device_type",
        SignalType.INTEGER,
        SignalCategory.COMPUTER_SYSTEM,
        "Device type code.",
        value_map={
            0: "desktop",
            1: "unknown",
            2: "smartphone",
            3: "tablet",
            4: "smart_tv",
            5: "connected_tv",
            6: "set_top_box",
            7: "connected_device",
        },
    ),
    Signal(
        "environment",
        SignalType.INTEGER,
        SignalCategory.COMPUTER_SYSTEM,
        "Serving environment.",
        value_map={
            10: "web_optimized",
            11: "web_not_optimized",
            12: "app",
        },
    ),
    Signal(
        "isp_reportable_id",
        SignalType.INTEGER,
        SignalCategory.COMPUTER_SYSTEM,
        "Internet Service Provider ID (Q3 2025 reportable_id ID space).",
    ),
    Signal(
        "language",
        SignalType.STRING,
        SignalCategory.COMPUTER_SYSTEM,
        "Browser language setting (string ID — see DV360 reference sheet).",
    ),
    Signal(
        "mobile_make_reportable_id",
        SignalType.INTEGER,
        SignalCategory.COMPUTER_SYSTEM,
        "Mobile manufacturer ID (Q3 2025 reportable_id ID space).",
    ),
    Signal(
        "mobile_model_reportable_id",
        SignalType.INTEGER,
        SignalCategory.COMPUTER_SYSTEM,
        "Mobile model ID (Q3 2025 reportable_id ID space).",
    ),
    Signal(
        "net_speed",
        SignalType.INTEGER,
        SignalCategory.COMPUTER_SYSTEM,
        "Network speed bucket.",
        value_map={
            1: "broadband_4g",
            2: "dialup",
            3: "unknown",
            4: "edge_2g",
            5: "umts_3g",
            6: "basic_dsl",
            7: "hsdpa_3_5g",
        },
    ),
    Signal(
        "operating_system_reportable_id",
        SignalType.INTEGER,
        SignalCategory.COMPUTER_SYSTEM,
        "Operating system ID (Q3 2025 reportable_id ID space).",
    ),
    # ─────── Serving (General) ───────
    Signal(
        "ad_position",
        SignalType.INTEGER,
        SignalCategory.SERVING,
        "Placement position.",
        value_map={0: "unknown", 1: "above_fold", 2: "below_fold"},
    ),
    Signal(
        "adx_page_categories",
        SignalType.LIST_OF_INTEGERS,
        SignalCategory.SERVING,
        "AdWords vertical IDs for the page content.",
    ),
    Signal(
        "channels",
        SignalType.LIST_OF_INTEGERS,
        SignalCategory.SERVING,
        "DV360 channel IDs.",
    ),
    Signal(
        "domain",
        SignalType.STRING,
        SignalCategory.SERVING,
        'Root domain (e.g. "example.com"). NOT available for CTV — use site_id.',
    ),
    Signal(
        "exchange_id",
        SignalType.INTEGER,
        SignalCategory.SERVING,
        "Exchange identifier.",
    ),
    Signal(
        "site_id",
        SignalType.INTEGER,
        SignalCategory.SERVING,
        "Site identifier (app/URL ID). Use this for CTV instead of domain.",
    ),
    # ─────── Active View ───────
    Signal(
        "active_view_measurable",
        SignalType.BOOLEAN,
        SignalCategory.ACTIVE_VIEW,
        "1 if the impression was measurable by Active View, else 0.",
    ),
    Signal(
        "active_view_viewed",
        SignalType.BOOLEAN,
        SignalCategory.ACTIVE_VIEW,
        "1 if Active View detected the ad as viewed, else 0.",
    ),
    # ─────── Event ───────
    Signal(
        "click",
        SignalType.BOOLEAN,
        SignalCategory.EVENT,
        "1 if the ad was clicked, else 0.",
    ),
    Signal(
        "time_on_screen_seconds",
        SignalType.INTEGER,
        SignalCategory.EVENT,
        "Time the ad was on screen, in seconds.",
    ),
    # ─────── Video ───────
    Signal(
        "audible",
        SignalType.BOOLEAN,
        SignalCategory.VIDEO,
        "RTB videos: 1 if sound was ON when viewed.",
    ),
    Signal(
        "completed_in_view_audible",
        SignalType.BOOLEAN,
        SignalCategory.VIDEO,
        "RTB videos: 1 if completed-in-view AND audible.",
    ),
    Signal(
        "video_completed",
        SignalType.BOOLEAN,
        SignalCategory.VIDEO,
        "1 if the video was completed (video ads only).",
    ),
    Signal(
        "video_player_height_start",
        SignalType.INTEGER,
        SignalCategory.VIDEO,
        "Video player height at first frame (px).",
    ),
    Signal(
        "video_player_size",
        SignalType.INTEGER,
        SignalCategory.VIDEO,
        "Player size bucket.",
        value_map={0: "unknown", 1: "small", 2: "large", 3: "hd"},
    ),
    Signal(
        "video_player_width_start",
        SignalType.INTEGER,
        SignalCategory.VIDEO,
        "Video player width at first frame (px).",
    ),
    Signal(
        "video_resized",
        SignalType.BINARY,
        SignalCategory.VIDEO,
        "1 if the player was resized during playback.",
    ),
    Signal(
        "viewable_on_complete",
        SignalType.BOOLEAN,
        SignalCategory.VIDEO,
        "RTB videos: 1 if viewed on completion.",
    ),
    Signal(
        "video_content_duration_bucket",
        SignalType.INTEGER,
        SignalCategory.VIDEO,
        "Video length bucket (1=0-1m, 2=1-5m, 3=5-15m, 4=15-30m, 5=30-60m, 7=60m+).",
        value_map={
            0: "unknown",
            1: "0_1m",
            2: "1_5m",
            3: "5_15m",
            4: "15_30m",
            5: "30_60m",
            7: "60m_plus",
        },
    ),
    Signal(
        "video_genre_ids",
        SignalType.LIST_OF_INTEGERS,
        SignalCategory.VIDEO,
        "Video genre IDs (see DV360 genre mapping).",
    ),
    Signal(
        "video_livestream",
        SignalType.BOOLEAN,
        SignalCategory.VIDEO,
        "True if the video is a livestream.",
    ),
    # ─────── Conversions (callables — take Floodlight Activity + Attribution Model) ───────
    Signal(
        "total_conversion_count",
        SignalType.DOUBLE,
        SignalCategory.CONVERSION,
        "Total conversion events for (Floodlight Activity ID, Attribution Model ID). "
        "Use 0 for the model_id to get last-touch attribution.",
        is_callable=True,
        arg_names=("floodlight_activity_id", "attribution_model_id"),
    ),
    Signal(
        "total_conversion_value",
        SignalType.DOUBLE,
        SignalCategory.CONVERSION,
        "Revenue from Floodlight Sales tags for (Activity ID, Model ID).",
        is_callable=True,
        arg_names=("floodlight_activity_id", "attribution_model_id"),
    ),
    Signal(
        "total_conversion_quantity",
        SignalType.DOUBLE,
        SignalCategory.CONVERSION,
        "Total conversion quantity for (Activity ID, Model ID).",
        is_callable=True,
        arg_names=("floodlight_activity_id", "attribution_model_id"),
    ),
    Signal(
        "conversion_custom_variable",
        SignalType.STRING,
        SignalCategory.CONVERSION,
        "Custom variable string for the latest attributed conversion.",
        is_callable=True,
        arg_names=("floodlight_activity_id", "attribution_model_id", "custom_variable_index"),
    ),
    Signal(
        "conversion_variable_num",
        SignalType.INTEGER,
        SignalCategory.CONVERSION,
        "Numeric 'num' Floodlight variable from the latest attributed conversion.",
        is_callable=True,
        arg_names=("floodlight_activity_id", "attribution_model_id"),
    ),
    Signal(
        "conversion_variable_ord",
        SignalType.STRING,
        SignalCategory.CONVERSION,
        "String 'ord' Floodlight variable from the latest attributed conversion.",
        is_callable=True,
        arg_names=("floodlight_activity_id", "attribution_model_id"),
    ),
)


# ─────────────────────────────────────────────────────────────── built-in fns


BUILTIN_FUNCTIONS: Final[tuple[BuiltinFunction, ...]] = (
    # Aggregate functions — these are the *only* legal way to compose
    # multiple criteria into a single score.
    BuiltinFunction(
        "first_match_aggregate",
        SignalType.DOUBLE,
        "Returns the weight of the first criteria in the list that is true.",
        params=(("criteria_pairs", "list"),),
    ),
    BuiltinFunction(
        "max_aggregate",
        SignalType.DOUBLE,
        "Returns the highest weight among criteria pairs that are true.",
        params=(("criteria_pairs", "list"),),
    ),
    BuiltinFunction(
        "sum_aggregate",
        SignalType.DOUBLE,
        "Returns the sum of weights across all true criteria pairs.",
        params=(("criteria_pairs", "list"),),
    ),
    # Casting
    BuiltinFunction("bool", SignalType.BOOLEAN, "Casts to boolean.", (("x", "any"),)),
    BuiltinFunction("float", SignalType.DOUBLE, "Casts to float.", (("x", "any"),)),
    BuiltinFunction("int", SignalType.INTEGER, "Casts to integer.", (("x", "any"),)),
    BuiltinFunction("str", SignalType.STRING, "Casts to string.", (("x", "any"),)),
    # Math
    BuiltinFunction(
        "log",
        SignalType.DOUBLE,
        "Natural log of x, or log(x)/log(base) if base provided.",
        params=(("x", "double"),),  # second arg `base` is optional
    ),
)


# ─────────────────────────────────────────────────────────────── reverse maps


SIGNALS_BY_NAME: Final[dict[str, Signal]] = {s.name: s for s in SIGNALS}
"""Quick lookup: signal-name → Signal."""

FUNCTIONS_BY_NAME: Final[dict[str, BuiltinFunction]] = {
    f.name: f for f in BUILTIN_FUNCTIONS
}

AGGREGATE_FUNCTIONS: Final[frozenset[str]] = frozenset({
    "first_match_aggregate",
    "max_aggregate",
    "sum_aggregate",
})

CASTING_FUNCTIONS: Final[frozenset[str]] = frozenset({"bool", "float", "int", "str"})

MATH_FUNCTIONS: Final[frozenset[str]] = frozenset({"log"})

ALL_ALLOWED_NAMES: Final[frozenset[str]] = frozenset(
    set(SIGNALS_BY_NAME) | set(FUNCTIONS_BY_NAME) | {"None", "True", "False"}
)
"""Union of every identifier the validator accepts as a free name."""


# ────────────────────────────────────────────────────────────────── helpers


def signal(name: str) -> Signal:
    """Lookup a signal by name; raises KeyError with a helpful suggestion."""
    if name in SIGNALS_BY_NAME:
        return SIGNALS_BY_NAME[name]
    raise KeyError(
        f"unknown DV360 custom-bidding signal {name!r}. "
        f"Did you mean one of: {sorted(s for s in SIGNALS_BY_NAME if name[:4] in s)[:5]}?"
    )


def signals_in_category(category: SignalCategory) -> list[Signal]:
    """All signals in a category, in their declaration order."""
    return [s for s in SIGNALS if s.category == category]


def is_allowed_identifier(name: str) -> bool:
    """True iff ``name`` is a signal, builtin, or sandbox-safe keyword."""
    return name in ALL_ALLOWED_NAMES
