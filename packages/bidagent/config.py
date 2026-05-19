"""Config loader. YAML on disk → dataclasses we trust.

Kept dependency-light: PyYAML only. No pydantic at this stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import HygieneRules, OptimizerConfig


@dataclass
class LineItemConfig:
    """Per-Line-Item configuration: target + which dimensions to manage."""

    line_item_id: int
    line_item_name: str
    bid_modifier_id: int                # ID of the bid_modifier object in Buzz
    cpv_target: float
    visit_event_id: int                 # conversion event ID for "visit"
    current_max_bid: float
    # Sprint 0 levers (Engine A — Bid Modifiers).
    # `time` covers dayparting via the `hour_of_day` key (TARGETING_TYPE_DAY_AND_TIME).
    # `audience` covers segment-level bid multipliers (TARGETING_TYPE_AUDIENCE_GROUP).
    targeting_modules: list[str] = field(default_factory=lambda: [
        "time", "platform", "device", "geo", "inventory", "audience",
    ])


@dataclass
class BuzzCredentials:
    """Reference to where the credentials live, not the credentials themselves."""

    base_url: str                       # e.g. https://customer.api.beeswax.com
    secret_ref: str                     # AWS Secrets Manager ARN or env var name
    auth_type: str = "cookie"           # "cookie" (default) or "api_key"


@dataclass
class AntennaConfig:
    """Where Antenna SQL lives."""

    connection_ref: str                 # env var or secret ref with the DSN
    schema: str = "antenna"
    window_days: int = 14               # rolling window for observation


@dataclass
class DigestConfig:
    """Digest delivery + LLM settings."""

    enabled: bool = True
    language: str = "it"                # "it" or "en"
    delivery: list[str] = field(default_factory=lambda: ["email"])  # email, slack, file
    email_to: list[str] = field(default_factory=list)
    slack_webhook_ref: str = ""         # secret ref
    llm_provider: str = "anthropic"     # "anthropic" | "openai" | "none"
    llm_model: str = "claude-sonnet-4-6"
    llm_key_ref: str = ""               # secret ref


@dataclass
class AppConfig:
    """Root config object."""

    name: str
    optimizer: OptimizerConfig
    hygiene: HygieneRules
    line_items: list[LineItemConfig]
    buzz: BuzzCredentials
    antenna: AntennaConfig
    digest: DigestConfig
    dry_run: bool = True                # never apply changes by default


def load_config(path: str | Path) -> AppConfig:
    """Load and validate a YAML config file into an AppConfig."""

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    optimizer = OptimizerConfig(**(raw.get("optimizer") or {"cpv_target": 0.5}))
    hygiene = HygieneRules(**(raw.get("hygiene") or {}))
    buzz = BuzzCredentials(**raw["buzz"])
    antenna = AntennaConfig(**raw["antenna"])
    digest = DigestConfig(**(raw.get("digest") or {}))

    line_items = [LineItemConfig(**li) for li in raw.get("line_items", [])]
    if not line_items:
        raise ValueError("Config must define at least one line_items entry.")

    return AppConfig(
        name=raw.get("name", "bidagent"),
        optimizer=optimizer,
        hygiene=hygiene,
        line_items=line_items,
        buzz=buzz,
        antenna=antenna,
        digest=digest,
        dry_run=bool(raw.get("dry_run", True)),
    )
