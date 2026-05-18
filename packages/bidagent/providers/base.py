"""Abstract provider interfaces.

The bidagent core (decision engine, digest generator, multi-objective
scorer) works exclusively on canonical data classes from
`bidagent.models` (`TermMetric`, `ModifierTerm`, `Plan`). It does not
care which programmatic platform produced the metrics or will apply
the bid changes.

This module formalizes that boundary with two abstract roles:

- `MetricsProvider` — reads observed performance for a line item.
- `BidProvider` — reads & writes current bid modifiers for a line item.

A platform implementation (DV360 today, TTD tomorrow)
provides concrete subclasses of these two and registers them with the
`ProviderRegistry`.

Design notes
------------
- Interfaces only. No I/O, no HTTP, no provider imports.
- Synchronous by default. Async-heavy providers (DV360 Reporting) wrap
  polling internally.
- Each method documents the **canonical** types it speaks. Provider
  modules are responsible for translating to/from their wire formats.
- The registry is process-local and does not persist anywhere. The API
  layer is expected to look up the right credentials per request.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..models import ModifierTerm, Plan, TermMetric


class ProviderCredentials(ABC):
    """Marker base class for opaque per-provider credential bags.

    Concrete providers subclass this with their own fields (e.g.
    `Dv360Credentials(client_id, client_secret, refresh_token)`).
    Keeping it opaque means call sites can be written against the
    abstract type without leaking provider details.
    """


@dataclass
class ApplyResult:
    """Outcome of attempting to apply a Plan via a BidProvider.

    Intentionally provider-agnostic. The `raw` field carries
    provider-specific response bodies for debugging only.
    """

    ok: bool
    dry_run: bool
    summary: str = ""
    raw: Any = None
    errors: list[str] = field(default_factory=list)


class MetricsProvider(ABC):
    """Reads observed performance for a single line item over a window.

    Implementations:
    - Translate the line item's external id into the provider's hierarchy.
    - Fetch impressions / clicks / visits / spend per targeting term.
    - Return a flat list of canonical `TermMetric` objects.
    """

    #: Stable identifier (e.g. "dv360", "ttd"). Used by the
    #: registry and stored alongside each tenant integration.
    provider_id: str = "abstract"

    @abstractmethod
    def fetch_week_metrics(
        self,
        line_item_external_id: str,
        week_start: date,
        week_end: date,
    ) -> list[TermMetric]:
        """Return canonical TermMetric rows for the window [start, end].

        Window endpoints are inclusive. Implementations may map a single
        call onto an async / polling workflow (e.g. AMC) and block until
        results are available, or onto a synchronous reporting API.

        Raises:
            RuntimeError: when the upstream reporting layer fails in a
                way the caller should not silently retry.
        """


class BidProvider(ABC):
    """Reads and writes current bid modifiers for a single line item.

    Implementations translate between the canonical `ModifierTerm`
    vocabulary and the platform's wire format.
    """

    provider_id: str = "abstract"

    @abstractmethod
    def get_current_modifiers(
        self,
        line_item_external_id: str,
    ) -> list[ModifierTerm]:
        """Return the modifiers currently configured for the line item.

        Implementations must translate provider-specific shapes into
        canonical `ModifierTerm` so the decision engine can compare
        against its own outputs.
        """

    @abstractmethod
    def apply_plan(
        self,
        plan: Plan,
        dry_run: bool = True,
    ) -> ApplyResult:
        """Apply (or simulate) the decisions in `plan`.

        - `dry_run=True` must NOT make state-changing calls. It validates
          the payload shape and returns a result with `dry_run=True`.
        - `dry_run=False` performs the actual writes.

        Implementations are responsible for batching, retries, and
        partial-failure handling. They report through `ApplyResult`.
        """


class ProviderRegistry:
    """Process-local lookup from provider_id to (MetricsProvider, BidProvider).

    Usage:
        registry = ProviderRegistry()
        registry.register("dv360", metrics_factory, bids_factory)
        m, b = registry.build("dv360", credentials=...)

    Each "factory" is a zero-arg-friendly callable that takes the
    credentials object and returns the provider instance. We do not
    cache instances here — the caller is expected to manage lifetime
    (typically one instance per request / per scheduled run).
    """

    def __init__(self) -> None:
        self._metrics_factories: dict[str, Any] = {}
        self._bids_factories: dict[str, Any] = {}

    def register(
        self,
        provider_id: str,
        metrics_factory: Any,
        bids_factory: Any,
    ) -> None:
        self._metrics_factories[provider_id] = metrics_factory
        self._bids_factories[provider_id] = bids_factory

    def available(self) -> list[str]:
        return sorted(
            set(self._metrics_factories) & set(self._bids_factories)
        )

    def build(
        self,
        provider_id: str,
        credentials: Optional[ProviderCredentials] = None,
        **kwargs: Any,
    ) -> tuple[MetricsProvider, BidProvider]:
        if provider_id not in self._metrics_factories:
            raise KeyError(
                f"No metrics provider registered for '{provider_id}'. "
                f"Available: {self.available()}"
            )
        if provider_id not in self._bids_factories:
            raise KeyError(
                f"No bid provider registered for '{provider_id}'. "
                f"Available: {self.available()}"
            )
        metrics = self._metrics_factories[provider_id](credentials, **kwargs)
        bids = self._bids_factories[provider_id](credentials, **kwargs)
        return metrics, bids
