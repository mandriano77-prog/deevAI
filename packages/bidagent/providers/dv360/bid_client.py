"""DV360 line-item targeting / bid multiplier client — live implementation.

Bid adjustments in DV360 are NOT a separate "rules" resource (as in
DV360 line items). Bid modifiers live on the line item's **assignedTargetingOptions**:
each assigned option can carry a `bidMultiplier` field that scales the
base bid for impressions matching that targeting term.

Endpoints used:
  GET  /v4/advertisers/{aid}/lineItems/{liid}/targetingTypes/{type}/assignedTargetingOptions
  POST /v4/advertisers/{aid}/lineItems/{liid}:bulkUpdate
       (bulkEditAssignedTargetingOptions semantics)

For per-line-item bid multiplier updates we use the bulk endpoint:
  POST /v4/advertisers/{aid}/lineItems/bulkEditAssignedTargetingOptions
which accepts a list of (line_item_id, create/delete) tuples and runs
the changes atomically.

Reference:
  https://developers.google.com/display-video/api/reference/rest/v4/advertisers.lineItems
  https://developers.google.com/display-video/api/reference/rest/v4/advertisers.lineItems.targetingTypes.assignedTargetingOptions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import requests

from ...models import ModifierTerm, Plan
from .auth import Dv360Auth

log = logging.getLogger(__name__)

DV360_API_BASE = "https://displayvideo.googleapis.com/v4"

PATH_ASSIGNED = (
    "/advertisers/{advertiserId}/lineItems/{lineItemId}"
    "/targetingTypes/{targetingType}/assignedTargetingOptions"
)
PATH_BULK_EDIT = (
    "/advertisers/{advertiserId}/lineItems:bulkEditAssignedTargetingOptions"
)

# Canonical (module, key) → DV360 TargetingType enum
CANONICAL_TO_TARGETING_TYPE: dict[tuple[str, str], str] = {
    ("inventory", "domain"): "TARGETING_TYPE_INVENTORY_SOURCE",
    ("inventory", "app"): "TARGETING_TYPE_APP",
    ("device", "device_type"): "TARGETING_TYPE_DEVICE_TYPE",
    ("geo", "country"): "TARGETING_TYPE_GEO_REGION",
    ("geo", "region"): "TARGETING_TYPE_GEO_REGION",
    ("geo", "city"): "TARGETING_TYPE_GEO_REGION",
    ("audience", "id"): "TARGETING_TYPE_AUDIENCE_GROUP",
}

# DV360 device-type enum tokens (used in targetingOptionId)
DEVICE_VALUE_MAP: dict[str, str] = {
    "MOBILE": "DEVICE_TYPE_SMART_PHONE",
    "PHONE": "DEVICE_TYPE_SMART_PHONE",
    "DESKTOP": "DEVICE_TYPE_COMPUTER",
    "PC": "DEVICE_TYPE_COMPUTER",
    "TABLET": "DEVICE_TYPE_TABLET",
    "CTV": "DEVICE_TYPE_CONNECTED_TV",
    "TV": "DEVICE_TYPE_CONNECTED_TV",
    "CONNECTED_TV": "DEVICE_TYPE_CONNECTED_TV",
    "SETTOPBOX": "DEVICE_TYPE_SET_TOP_BOX",
}


class Dv360BidClientError(RuntimeError):
    """Raised when a DV360 line-item API call fails non-recoverably."""


@dataclass
class Dv360ApiResult:
    """Result envelope for DV360 bulkEdit calls."""

    ok: bool
    status_code: int
    body: Any
    dry_run: bool = False
    note: str = ""


class Dv360LineItemClient:
    """Client for DV360 line item targeting / bid multiplier writes.

    Reads (list assigned targeting) and writes (bulkEdit) both go
    through the injected `session` so tests can mock them.
    """

    def __init__(
        self,
        auth: Dv360Auth,
        session: Optional[requests.Session] = None,
        dry_run: bool = True,
        timeout_seconds: int = 20,
    ) -> None:
        self.auth = auth
        self.dry_run = dry_run
        self._session = session or requests.Session()
        self._timeout = timeout_seconds

    # ---------------------------------------------------------------- helpers

    def _url(self, path: str, **fmt: Any) -> str:
        return DV360_API_BASE + path.format(**fmt)

    def _get(self, path: str, **fmt: Any) -> Dv360ApiResult:
        url = self._url(path, **fmt)
        try:
            resp = self._session.get(
                url, headers=self.auth.headers(), timeout=self._timeout
            )
        except requests.RequestException as exc:
            return Dv360ApiResult(ok=False, status_code=0, body=None,
                                  note=f"transport error: {exc}")
        body: Any
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        return Dv360ApiResult(
            ok=200 <= resp.status_code < 300,
            status_code=resp.status_code,
            body=body,
            note="" if resp.status_code < 300 else f"http {resp.status_code}",
        )

    def _post(self, path: str, json_body: dict[str, Any], **fmt: Any) -> Dv360ApiResult:
        url = self._url(path, **fmt)
        try:
            resp = self._session.post(
                url,
                headers=self.auth.headers(),
                json=json_body,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            return Dv360ApiResult(ok=False, status_code=0, body=None,
                                  note=f"transport error: {exc}")
        body: Any
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        return Dv360ApiResult(
            ok=200 <= resp.status_code < 300,
            status_code=resp.status_code,
            body=body,
            note="" if resp.status_code < 300 else f"http {resp.status_code}",
        )

    # ------------------------------------------------------------------ API

    def list_assigned_targeting(
        self,
        advertiser_id: str,
        line_item_id: str,
        targeting_type: str,
    ) -> Dv360ApiResult:
        """List assigned options for a single targeting type on a line item.

        DV360 requires one call per targeting type. Callers needing all
        types should iterate over `CANONICAL_TO_TARGETING_TYPE.values()`.
        """
        return self._get(
            PATH_ASSIGNED,
            advertiserId=advertiser_id,
            lineItemId=line_item_id,
            targetingType=targeting_type,
        )

    def bulk_edit_targeting(
        self,
        advertiser_id: str,
        body: dict[str, Any],
    ) -> Dv360ApiResult:
        """POST advertisers.lineItems.bulkEditAssignedTargetingOptions.

        The body must include `lineItemIds`, `createRequests`,
        `deleteRequests`. See `build_bulk_edit_body`.
        """
        if self.dry_run:
            return Dv360ApiResult(
                ok=True,
                status_code=0,
                body=body,
                dry_run=True,
                note="[dry-run] no HTTP request was sent",
            )
        return self._post(PATH_BULK_EDIT, body, advertiserId=advertiser_id)


# ---------------------------------------------------------------------------
# Translation helpers
# ---------------------------------------------------------------------------


def _to_dv360_value(canonical: tuple[str, str], value: str) -> str:
    if canonical == ("device", "device_type"):
        return DEVICE_VALUE_MAP.get(value.upper(), value)
    return value


def to_dv360_assigned_option(term: ModifierTerm) -> Optional[dict[str, Any]]:
    """Translate a canonical ModifierTerm into a DV360 AssignedTargetingOption.

    Returns None if the term's (module, key) is not supported by DV360.

    Note: the actual `assignedTargetingOptionDetails` field name varies
    per targeting type (e.g. `deviceTypeDetails` for device, `appDetails`
    for app). For PoC-level shape we use a generic envelope; production
    must switch on `targetingType` and emit the precise per-type detail
    object expected by DV360. The mapping below covers the canonical
    families our engine emits.
    """
    canonical = (term.targeting_module, term.targeting_key)
    targeting_type = CANONICAL_TO_TARGETING_TYPE.get(canonical)
    if not targeting_type:
        return None
    value_token = _to_dv360_value(canonical, str(term.value))

    # Per-type details envelope. Keys follow DV360 API v4 names.
    details_key = {
        "TARGETING_TYPE_DEVICE_TYPE": "deviceTypeDetails",
        "TARGETING_TYPE_APP": "appDetails",
        "TARGETING_TYPE_INVENTORY_SOURCE": "inventorySourceDetails",
        "TARGETING_TYPE_GEO_REGION": "geoRegionDetails",
        "TARGETING_TYPE_AUDIENCE_GROUP": "audienceGroupDetails",
    }.get(targeting_type, "details")

    return {
        "targetingType": targeting_type,
        details_key: {
            "targetingOptionId": value_token,
            "bidMultiplier": round(term.modifier, 3),
        },
    }


def build_bulk_edit_body(plan: Plan) -> dict[str, Any]:
    """Build the body for advertisers.lineItems.bulkEditAssignedTargetingOptions.

    For each changed decision in the plan we emit:
    - a createRequest with the new bidMultiplier
    - a deleteRequest placeholder (caller fills assignedTargetingOptionIds
      after a prior list call; here we leave the list empty so a live
      apply path can plug it in without changing the function contract)

    Decisions whose targeting type DV360 doesn't support are skipped:
    the digest still mentions them because the engine is provider-blind.
    """
    create_requests: list[dict[str, Any]] = []
    delete_requests: list[dict[str, Any]] = []

    for decision in plan.changed_decisions:
        synthetic = ModifierTerm(
            targeting_module=decision.term.targeting_module,
            targeting_key=decision.term.targeting_key,
            value=decision.term.value,
            modifier=decision.new_modifier,
            field_label=decision.term.field_label,
        )
        option = to_dv360_assigned_option(synthetic)
        if not option:
            continue
        targeting_type = option["targetingType"]
        create_requests.append(
            {
                "targetingType": targeting_type,
                "assignedTargetingOptions": [option],
            }
        )
        delete_requests.append(
            {
                "targetingType": targeting_type,
                # In production: populate from a prior list_assigned_targeting
                # call cached per run. Empty list here means "no-op delete".
                "assignedTargetingOptionIds": [],
            }
        )

    return {
        "lineItemIds": [str(plan.line_item_id)],
        "createRequests": create_requests,
        "deleteRequests": delete_requests,
    }
