"""Provider abstraction layer for bidagent.

This subpackage introduces a thin, **additive** abstraction over the
existing platform-specific clients (today: DV360). It does
*not* modify any existing code paths — the legacy imports under
`bidagent.providers.dv360.*` is the reference implementation.

Goal: let callers add new DSPs (TTD, Beeswax, ...) in
the future by implementing the same interfaces, without touching the
decision engine, the digest generator, or the API service layer.

See `docs/MULTI_PROVIDER_REFACTOR.md` for the broader plan.
"""

from .base import (
    ApplyResult,
    BidProvider,
    MetricsProvider,
    ProviderCredentials,
    ProviderRegistry,
)

__all__ = [
    "ApplyResult",
    "BidProvider",
    "MetricsProvider",
    "ProviderCredentials",
    "ProviderRegistry",
]
