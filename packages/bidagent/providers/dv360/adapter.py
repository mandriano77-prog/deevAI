"""DV360 adapter — concrete providers + registry wiring.

Two implementations:

1. `Dv360MetricsProvider` + `Dv360BidProvider`
   - Real wrappers around `Dv360ReportingClient` and `Dv360LineItemClient`.
   - Use OAuth user-consent (refresh_token flow). HTTP is real, but the
     `session` argument can be injected to mock it in tests.

2. `Dv360MockMetricsProvider` + `Dv360MockBidProvider`
   - Backed by `mock_data.py`. No network. Deterministic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

import requests

from ...models import ModifierTerm, Plan, TermMetric
from ..base import (
    ApplyResult,
    BidProvider,
    MetricsProvider,
    ProviderCredentials,
    ProviderRegistry,
)

log = logging.getLogger(__name__)


@dataclass
class Dv360ProviderCredentials(ProviderCredentials):
    """OAuth credentials + per-tenant scope.

    `partner_id` is optional — not every reporting call needs it, but
    we store it for completeness (DV360 hierarchy is Partner →
    Advertiser → Campaign → IO → LineItem).
    """

    client_id: str
    client_secret: str
    refresh_token: str

    partner_id: Optional[str] = None
    advertiser_id: Optional[str] = None
    timezone_code: str = "Europe/Rome"


# ---------------------------------------------------------------------------
# Real wrappers — live HTTP, session-injectable
# ---------------------------------------------------------------------------


class Dv360MetricsProvider(MetricsProvider):
    """Wraps `Dv360ReportingClient`. Live HTTP."""

    provider_id = "dv360"

    def __init__(
        self,
        credentials: Dv360ProviderCredentials,
        session: Optional[requests.Session] = None,
    ) -> None:
        from .auth import Dv360Auth, Dv360Credentials
        from .metrics_client import Dv360ReportingClient, Dv360ReportingConfig

        if not credentials.advertiser_id:
            raise ValueError("Dv360MetricsProvider requires advertiser_id.")

        creds = Dv360Credentials(
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            refresh_token=credentials.refresh_token,
        )
        # Share the same session between the auth refresh and the reporting
        # calls so connection pooling / mocks work end-to-end.
        self._session = session or requests.Session()
        self._auth = Dv360Auth(creds, session=self._session)
        self._cfg = Dv360ReportingConfig(
            partner_id=credentials.partner_id or "",
            advertiser_id=credentials.advertiser_id,
            timezone_code=credentials.timezone_code,
        )
        self._client = Dv360ReportingClient(self._auth, self._cfg, session=self._session)

    def fetch_week_metrics(
        self,
        line_item_external_id: str,
        week_start: date,
        week_end: date,
    ) -> list[TermMetric]:
        from .metrics_client import (
            build_dimension_query_spec,
            parse_csv,
            rows_to_metrics,
        )

        spec = build_dimension_query_spec(
            advertiser_id=self._cfg.advertiser_id,
            line_item_id=line_item_external_id,
            week_start=week_start,
            week_end=week_end,
            timezone_code=self._cfg.timezone_code,
        )
        query_id = self._client.create_query(spec)
        report_id = self._client.run_query(query_id)
        meta = self._client.wait_report(query_id, report_id)

        # DV360 metadata gives us a Cloud Storage signed URL.
        download_url = (
            (meta.get("metadata") or {}).get("googleCloudStoragePath")
            or (meta.get("metadata") or {}).get("googleDrivePath")
        )
        if not download_url:
            raise RuntimeError(
                f"DV360 report {report_id} reached DONE but exposes no "
                f"download URL. metadata keys: {list((meta.get('metadata') or {}).keys())}"
            )
        csv_text = self._client.fetch_csv(download_url)
        rows = parse_csv(csv_text)
        return rows_to_metrics(rows)


class Dv360BidProvider(BidProvider):
    """Wraps `Dv360LineItemClient`. Live HTTP."""

    provider_id = "dv360"

    def __init__(
        self,
        credentials: Dv360ProviderCredentials,
        session: Optional[requests.Session] = None,
    ) -> None:
        from .auth import Dv360Auth, Dv360Credentials
        from .bid_client import Dv360LineItemClient

        if not credentials.advertiser_id:
            raise ValueError("Dv360BidProvider requires advertiser_id.")

        creds = Dv360Credentials(
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            refresh_token=credentials.refresh_token,
        )
        self._session = session or requests.Session()
        self._auth = Dv360Auth(creds, session=self._session)
        self._client = Dv360LineItemClient(
            self._auth, session=self._session, dry_run=True
        )
        self._credentials = credentials

    def get_current_modifiers(
        self,
        line_item_external_id: str,
    ) -> list[ModifierTerm]:
        from .bid_client import CANONICAL_TO_TARGETING_TYPE

        # We iterate over the canonical targeting types we care about
        # and union the assigned options. Each missing/empty type is
        # silently skipped (line items often have only a subset).
        out: list[ModifierTerm] = []
        seen: set[tuple[str, str, str]] = set()
        for canonical, targeting_type in CANONICAL_TO_TARGETING_TYPE.items():
            result = self._client.list_assigned_targeting(
                advertiser_id=self._credentials.advertiser_id or "",
                line_item_id=line_item_external_id,
                targeting_type=targeting_type,
            )
            if not result.ok or not isinstance(result.body, dict):
                continue
            options = result.body.get("assignedTargetingOptions", []) or []
            for opt in options:
                # The detail object key varies by targeting type. Find it.
                details: Optional[dict[str, Any]] = None
                for v in opt.values():
                    if isinstance(v, dict) and "bidMultiplier" in v:
                        details = v
                        break
                if not details:
                    continue
                value = (
                    details.get("targetingOptionId")
                    or details.get("displayName")
                    or ""
                )
                if not value:
                    continue
                key = (canonical[0], canonical[1], str(value))
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    ModifierTerm(
                        targeting_module=canonical[0],
                        targeting_key=canonical[1],
                        value=str(value),
                        modifier=float(details.get("bidMultiplier") or 1.0),
                        field_label=str(details.get("displayName") or value),
                    )
                )
        return out

    def apply_plan(self, plan: Plan, dry_run: bool = True) -> ApplyResult:
        from .bid_client import build_bulk_edit_body

        body = build_bulk_edit_body(plan)
        if dry_run:
            return ApplyResult(
                ok=True,
                dry_run=True,
                summary=(
                    f"[dry-run] would bulk-edit "
                    f"{len(body.get('createRequests', []))} create / "
                    f"{len(body.get('deleteRequests', []))} delete "
                    f"requests on DV360 line item {plan.line_item_id}"
                ),
                raw=body,
            )
        # Live application.
        self._client.dry_run = False
        try:
            result = self._client.bulk_edit_targeting(
                advertiser_id=self._credentials.advertiser_id or "",
                body=body,
            )
            return ApplyResult(
                ok=result.ok,
                dry_run=False,
                summary=result.note or "applied",
                raw=result.body,
                errors=[] if result.ok else [f"http {result.status_code}"],
            )
        finally:
            self._client.dry_run = True  # restore safe default


# ---------------------------------------------------------------------------
# Mock providers (network-free, deterministic)
# ---------------------------------------------------------------------------


class Dv360MockMetricsProvider(MetricsProvider):
    """Returns deterministic DV360-shaped fake metrics."""

    provider_id = "dv360_mock"

    def __init__(self, credentials: Optional[ProviderCredentials] = None) -> None:
        self._credentials = credentials

    def fetch_week_metrics(
        self,
        line_item_external_id: str,
        week_start: date,
        week_end: date,
    ) -> list[TermMetric]:
        from .mock_data import fake_dv360_week_metrics

        return fake_dv360_week_metrics(seed=7)


class Dv360MockBidProvider(BidProvider):
    """Mock equivalent of Dv360BidProvider — no network, no writes."""

    provider_id = "dv360_mock"

    def __init__(self, credentials: Optional[ProviderCredentials] = None) -> None:
        self._credentials = credentials

    def get_current_modifiers(
        self,
        line_item_external_id: str,
    ) -> list[ModifierTerm]:
        from .mock_data import fake_current_bid_multipliers, fake_dv360_week_metrics

        metrics = fake_dv360_week_metrics(seed=7)
        mults = fake_current_bid_multipliers(metrics)
        out: list[ModifierTerm] = []
        for m in metrics:
            key = (m.targeting_module, m.targeting_key, str(m.value))
            out.append(
                ModifierTerm(
                    targeting_module=m.targeting_module,
                    targeting_key=m.targeting_key,
                    value=m.value,
                    modifier=mults.get(key, 1.0),
                    field_label=m.field_label,
                )
            )
        return out

    def apply_plan(self, plan: Plan, dry_run: bool = True) -> ApplyResult:
        return ApplyResult(
            ok=True,
            dry_run=True,
            summary=(
                f"[mock-dv360] would apply plan with "
                f"{len(plan.decisions)} decisions "
                f"({sum(1 for d in plan.decisions if d.changed)} changed)"
            ),
            raw=None,
        )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def register_dv360_providers(registry: ProviderRegistry) -> None:
    """Register both real and mock DV360 providers on a registry instance."""
    registry.register(
        "dv360",
        metrics_factory=lambda creds, session=None, **_: Dv360MetricsProvider(creds, session=session),
        bids_factory=lambda creds, session=None, **_: Dv360BidProvider(creds, session=session),
    )
    registry.register(
        "dv360_mock",
        metrics_factory=lambda creds=None, **_: Dv360MockMetricsProvider(creds),
        bids_factory=lambda creds=None, **_: Dv360MockBidProvider(creds),
    )
