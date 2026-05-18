"""Google Display & Video 360 (DV360) provider for bidagent.

This subpackage implements the bidagent provider interface for
DV360 API v4 (`displayvideo.googleapis.com`) + DV360 Reporting API.

Status: scaffolding + mock providers + adapter wiring. Real wire
clients (`auth.py`, `metrics_client.py`, `bid_client.py`) declare the
API surface but are **not exercised against live Google endpoints in
this PoC**. They are structured to make the eventual integration a
matter of filling in the request payloads — not redesigning the layer.

See `docs/MULTI_PROVIDER_REFACTOR.md` for the broader plan.
"""

from .adapter import (
    Dv360BidProvider,
    Dv360MetricsProvider,
    Dv360MockBidProvider,
    Dv360MockMetricsProvider,
    Dv360ProviderCredentials,
    register_dv360_providers,
)

__all__ = [
    "Dv360BidProvider",
    "Dv360MetricsProvider",
    "Dv360MockBidProvider",
    "Dv360MockMetricsProvider",
    "Dv360ProviderCredentials",
    "register_dv360_providers",
]
