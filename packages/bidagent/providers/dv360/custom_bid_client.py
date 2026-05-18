"""Thin client for DV360 Custom Bidding endpoints (v4).

Authoritative source for the API surface is the discovery doc:
    https://displayvideo.googleapis.com/$discovery/rest?version=v4

Custom bidding has three Resources we care about:

1. ``customBiddingAlgorithms`` — the container/entity (algorithm + metadata)
2. ``customBiddingAlgorithms.scripts`` — versioned script files attached to it
3. ``media`` — Cloud Storage staging area for the actual script bytes

Upload is a **three-step ritual**, exactly as DV360 dictates:

    a. POST /v4/customBiddingAlgorithms             → algorithmId
    b. GET  /v4/customBiddingAlgorithms/{id}:uploadScript
                                                    → {resourceName}
    c. POST /upload/media/{resourceName}  (multipart, content=script)
                                                    → 200 OK
    d. POST /v4/customBiddingAlgorithms/{id}/scripts
            body={script:{resourceName: "..."}}
                                                    → {customBiddingScriptId, state}

(a) is once per advertiser+name. (b)→(d) is once per *new version*.
DV360 stores history; the most recent ACCEPTED script becomes the
``active`` one used for scoring.

This client mirrors ``bid_client.Dv360LineItemClient``: same auth
pattern, same dry-run switch, same ApiResult envelope. So the
orchestrator in ``services/`` can use both engines uniformly.

Tested via :mod:`tests.test_dv360_custom_bid_client_http` with a
mocked ``requests.Session`` — no real HTTP hits Google here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import requests

from .auth import Dv360Auth
from .bid_client import Dv360ApiResult  # reuse the same envelope

log = logging.getLogger(__name__)

# Standard DV360 API base — same as the bid client.
API_BASE = "https://displayvideo.googleapis.com/v4"
UPLOAD_BASE = "https://displayvideo.googleapis.com/upload"

# Path templates — keep them close to the methods so they're greppable.
PATH_ALGORITHMS = "/customBiddingAlgorithms"
PATH_ALGORITHM = "/customBiddingAlgorithms/{algorithm_id}"
PATH_UPLOAD_SCRIPT = "/customBiddingAlgorithms/{algorithm_id}:uploadScript"
PATH_SCRIPTS = "/customBiddingAlgorithms/{algorithm_id}/scripts"
PATH_SCRIPT = "/customBiddingAlgorithms/{algorithm_id}/scripts/{script_id}"


class Dv360CustomBidError(RuntimeError):
    """Raised on non-recoverable Custom Bidding API failures."""


@dataclass(frozen=True)
class UploadedScript:
    """The artefact you get back after a successful 3-step upload.

    ``state`` mirrors DV360's enum: PENDING, ACCEPTED, REJECTED. The
    state at script-creation time is almost always PENDING — DV360
    validates asynchronously and moves it to ACCEPTED or REJECTED
    within minutes.
    """

    algorithm_id: str
    script_id: str
    state: str
    raw: dict[str, Any]


class Dv360CustomBidClient:
    """DV360 Custom Bidding API client.

    Same wiring as ``Dv360LineItemClient``: inject auth + (optional)
    session for tests. ``dry_run=True`` makes every method log what
    it *would* do and return a synthetic ApiResult/UploadedScript
    without contacting Google.
    """

    def __init__(
        self,
        auth: Dv360Auth,
        session: Optional[requests.Session] = None,
        dry_run: bool = True,
        timeout_seconds: int = 30,
    ) -> None:
        self.auth = auth
        self.dry_run = dry_run
        self._session = session or requests.Session()
        self._timeout = timeout_seconds

    # ───────────────────────────────────────────────────────── helpers

    def _api_url(self, template: str, **fmt: Any) -> str:
        return f"{API_BASE}{template.format(**fmt)}"

    def _upload_url(self, resource_name: str) -> str:
        # ``resourceName`` from uploadScript already includes the
        # full storage path; DV360 appends "/upload" prefix to use it.
        return f"{UPLOAD_BASE}/media/{resource_name}"

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Dv360ApiResult:
        """One HTTP call with full ApiResult envelope.

        We always include ``alt=json`` so DV360 returns parseable JSON
        (the default for most endpoints, but explicit beats implicit).
        """
        if self.dry_run:
            log.info(
                "dv360_cbb DRY-RUN %s %s params=%s body_keys=%s",
                method, url, params, list((json or {}).keys()),
            )
            return Dv360ApiResult(
                ok=True, status_code=200, body={}, dry_run=True,
                note=f"[dry-run] {method} {url}",
            )

        merged_headers = self.auth.headers()
        if headers:
            merged_headers.update(headers)

        try:
            resp = self._session.request(
                method,
                url,
                params=params,
                json=json,
                data=data,
                headers=merged_headers,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            return Dv360ApiResult(
                ok=False, status_code=0, body=None,
                note=f"transport error: {exc}",
            )

        body: Any
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = resp.text[:1000]

        return Dv360ApiResult(
            ok=200 <= resp.status_code < 300,
            status_code=resp.status_code,
            body=body,
            note=f"http {resp.status_code}",
        )

    # ─────────────────────────────────────────────────────── algorithms

    def create_algorithm(
        self,
        *,
        display_name: str,
        advertiser_id: str | None = None,
        partner_id: str | None = None,
        algorithm_type: str = "SCRIPT_BASED",
        third_party_optimization_partner: str | None = None,
    ) -> Dv360ApiResult:
        """Create a Custom Bidding Algorithm.

        Exactly one of ``advertiser_id`` / ``partner_id`` must be set:
        advertiser-scoped algorithms are usable by that advertiser
        only; partner-scoped ones can be shared across advertisers
        under the partner.

        ``third_party_optimization_partner`` is reserved for Google-
        approved partners (currently SCIBIDS and ADELAIDE). Leave None
        unless deevAI is officially listed by Google. (Future work:
        apply for this slot.)
        """
        if (advertiser_id is None) == (partner_id is None):
            raise ValueError(
                "Provide exactly one of advertiser_id / partner_id."
            )
        if algorithm_type not in {"SCRIPT_BASED", "RULE_BASED"}:
            raise ValueError(
                "algorithm_type must be SCRIPT_BASED or RULE_BASED."
            )

        body: dict[str, Any] = {
            "displayName": display_name,
            "customBiddingAlgorithmType": algorithm_type,
            "entityStatus": "ENTITY_STATUS_ACTIVE",
        }
        if advertiser_id is not None:
            body["advertiserId"] = advertiser_id
        if partner_id is not None:
            body["partnerId"] = partner_id
        if third_party_optimization_partner:
            body["thirdPartyOptimizationPartner"] = third_party_optimization_partner

        return self._request(
            "POST",
            self._api_url(PATH_ALGORITHMS),
            json=body,
        )

    def get_algorithm(
        self,
        algorithm_id: str,
        *,
        advertiser_id: str | None = None,
        partner_id: str | None = None,
    ) -> Dv360ApiResult:
        params: dict[str, Any] = {}
        if advertiser_id:
            params["advertiserId"] = advertiser_id
        if partner_id:
            params["partnerId"] = partner_id
        return self._request(
            "GET",
            self._api_url(PATH_ALGORITHM, algorithm_id=algorithm_id),
            params=params,
        )

    # ──────────────────────────────────────────── 3-step script upload

    def request_upload_url(
        self,
        algorithm_id: str,
        *,
        advertiser_id: str | None = None,
        partner_id: str | None = None,
    ) -> Dv360ApiResult:
        """Step 2 of the upload ritual — ask DV360 for a staging URL.

        DV360 returns ``{resourceName: "customBiddingAlgorithms/…"}``.
        Pass that into :meth:`upload_script_bytes`.
        """
        params: dict[str, Any] = {}
        if advertiser_id:
            params["advertiserId"] = advertiser_id
        if partner_id:
            params["partnerId"] = partner_id
        return self._request(
            "GET",
            self._api_url(PATH_UPLOAD_SCRIPT, algorithm_id=algorithm_id),
            params=params,
        )

    def upload_script_bytes(
        self,
        resource_name: str,
        script_source: str,
    ) -> Dv360ApiResult:
        """Step 3 — stream the script bytes to the upload URL.

        DV360 wants ``text/plain``. We always UTF-8 encode. A 200 with
        empty body is the success signal.
        """
        if self.dry_run:
            log.info(
                "dv360_cbb DRY-RUN upload bytes=%d resource_name=%s",
                len(script_source.encode("utf-8")),
                resource_name,
            )
            return Dv360ApiResult(
                ok=True, status_code=200, body={}, dry_run=True,
                note=f"[dry-run] upload {len(script_source)} chars",
            )

        return self._request(
            "POST",
            self._upload_url(resource_name),
            data=script_source.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )

    def register_script(
        self,
        algorithm_id: str,
        resource_name: str,
        *,
        advertiser_id: str | None = None,
        partner_id: str | None = None,
    ) -> Dv360ApiResult:
        """Step 4 — POST a new CustomBiddingScript referencing the
        uploaded bytes.

        DV360 enqueues server-side validation; the response carries
        ``state=PENDING`` initially. Poll with :meth:`get_script` to
        observe ACCEPTED / REJECTED.
        """
        params: dict[str, Any] = {}
        if advertiser_id:
            params["advertiserId"] = advertiser_id
        if partner_id:
            params["partnerId"] = partner_id
        body = {"script": {"resourceName": resource_name}}
        return self._request(
            "POST",
            self._api_url(PATH_SCRIPTS, algorithm_id=algorithm_id),
            params=params,
            json=body,
        )

    def get_script(
        self,
        algorithm_id: str,
        script_id: str,
        *,
        advertiser_id: str | None = None,
        partner_id: str | None = None,
    ) -> Dv360ApiResult:
        params: dict[str, Any] = {}
        if advertiser_id:
            params["advertiserId"] = advertiser_id
        if partner_id:
            params["partnerId"] = partner_id
        return self._request(
            "GET",
            self._api_url(
                PATH_SCRIPT, algorithm_id=algorithm_id, script_id=script_id,
            ),
            params=params,
        )

    # ───────────────────────────────────────────── high-level convenience

    def upload_full_script(
        self,
        algorithm_id: str,
        script_source: str,
        *,
        advertiser_id: str | None = None,
        partner_id: str | None = None,
    ) -> UploadedScript:
        """Run the full 3-step upload sequence and return an
        :class:`UploadedScript`.

        Raises:
            Dv360CustomBidError: at the first non-2xx response. The
                error carries the step name + raw DV360 detail so
                operators can see exactly where the pipeline broke.
        """
        # Step 2 — staging URL
        step2 = self.request_upload_url(
            algorithm_id,
            advertiser_id=advertiser_id,
            partner_id=partner_id,
        )
        if not step2.ok:
            raise Dv360CustomBidError(
                f"uploadScript failed (step 2/4): {step2.note} body={step2.body}"
            )
        resource_name = (
            step2.body.get("resourceName") if isinstance(step2.body, dict) else None
        )
        if not resource_name:
            # In dry-run we synthesise a plausible value so the caller
            # can keep walking through the steps in tests.
            if self.dry_run:
                resource_name = (
                    f"customBiddingAlgorithms/{algorithm_id}/scriptRefs/dryrun"
                )
            else:
                raise Dv360CustomBidError(
                    "uploadScript returned no resourceName"
                )

        # Step 3 — bytes
        step3 = self.upload_script_bytes(resource_name, script_source)
        if not step3.ok:
            raise Dv360CustomBidError(
                f"media upload failed (step 3/4): {step3.note}"
            )

        # Step 4 — register
        step4 = self.register_script(
            algorithm_id,
            resource_name,
            advertiser_id=advertiser_id,
            partner_id=partner_id,
        )
        if not step4.ok:
            raise Dv360CustomBidError(
                f"scripts.create failed (step 4/4): {step4.note} body={step4.body}"
            )

        body = step4.body if isinstance(step4.body, dict) else {}
        return UploadedScript(
            algorithm_id=algorithm_id,
            script_id=str(body.get("customBiddingScriptId", "dryrun")),
            state=str(body.get("state", "PENDING")),
            raw=body,
        )
