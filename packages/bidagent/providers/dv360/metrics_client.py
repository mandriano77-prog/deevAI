"""DV360 reporting client — live HTTP implementation.

Pipeline:
  1. POST /v2/queries                       → queryId
  2. POST /v2/queries/{id}:run              → reportId (async)
  3. GET  /v2/queries/{id}/reports/{rid}    → poll until metadata.status = DONE
  4. GET  metadata.googleCloudStoragePath   → CSV bytes
  5. Parse CSV → list[TermMetric]

We do not stream the CSV: DV360 weekly reports for a single line item
are small (low thousands of rows at most), so a buffered fetch is fine.

The client takes an injected `requests.Session` so tests can swap it
out without monkey-patching globals.

Reference:
  https://developers.google.com/bid-manager/v2/queries
  https://developers.google.com/bid-manager/v2/reports
"""

from __future__ import annotations

import csv
import io
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import requests

from ...models import TermMetric
from .auth import Dv360Auth

log = logging.getLogger(__name__)

REPORTING_BASE_URL = "https://doubleclickbidmanager.googleapis.com/v2"

PATH_QUERIES = "/queries"
PATH_QUERIES_RUN = "/queries/{queryId}:run"
PATH_REPORT = "/queries/{queryId}/reports/{reportId}"

POLL_INTERVAL_SECONDS = 10
POLL_TIMEOUT_SECONDS = 60 * 20  # 20 min — DV360 reports usually finish in 1-3 min

# Canonical (module, key) → DV360 reporting dimension column name
DV360_DIMENSION_MAP: dict[tuple[str, str], str] = {
    ("inventory", "domain"): "FILTER_SITE_DCM",
    ("inventory", "app"): "FILTER_APP_ID",
    ("device", "device_type"): "FILTER_DEVICE_TYPE",
    ("geo", "country"): "FILTER_COUNTRY",
    ("geo", "region"): "FILTER_REGION",
    ("geo", "city"): "FILTER_CITY",
    ("audience", "id"): "FILTER_AUDIENCE_LIST",
}


@dataclass
class Dv360ReportingConfig:
    """Per-tenant configuration for the reporting API."""

    partner_id: str
    advertiser_id: str
    timezone_code: str = "Europe/Rome"


class Dv360ReportingError(RuntimeError):
    """Raised when a reporting call fails non-recoverably."""


@dataclass
class _PollState:
    """Internal: tracks elapsed time for the polling loop."""

    deadline: float
    interval: float = POLL_INTERVAL_SECONDS

    def expired(self) -> bool:
        return time.time() >= self.deadline


class Dv360ReportingClient:
    """Synchronous wrapper over DV360 Reporting API v2.

    All HTTP goes through the injected `session` so tests can mock it.
    """

    def __init__(
        self,
        auth: Dv360Auth,
        cfg: Dv360ReportingConfig,
        session: Optional[requests.Session] = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.auth = auth
        self.cfg = cfg
        self._session = session or requests.Session()
        self._timeout = timeout_seconds

    # ---------------------------------------------------------------- helpers

    def _url(self, path: str, **fmt: Any) -> str:
        return REPORTING_BASE_URL + path.format(**fmt)

    def _post(self, path: str, json_body: dict[str, Any], **fmt: Any) -> dict[str, Any]:
        url = self._url(path, **fmt)
        resp = self._session.post(
            url, headers=self.auth.headers(), json=json_body, timeout=self._timeout
        )
        if resp.status_code not in (200, 201):
            raise Dv360ReportingError(
                f"POST {url} → http {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json() or {}

    def _get_json(self, path: str, **fmt: Any) -> dict[str, Any]:
        url = self._url(path, **fmt)
        resp = self._session.get(
            url, headers=self.auth.headers(), timeout=self._timeout
        )
        if resp.status_code != 200:
            raise Dv360ReportingError(
                f"GET {url} → http {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json() or {}

    # ----------------------------------------------------------------- public

    def create_query(self, spec: dict[str, Any]) -> str:
        """POST /queries → return queryId."""
        body = self._post(PATH_QUERIES, spec)
        query_id = body.get("queryId")
        if not query_id:
            raise Dv360ReportingError(
                f"create_query response missing queryId (keys={list(body)})"
            )
        return str(query_id)

    def run_query(self, query_id: str) -> str:
        """POST /queries/{id}:run → return reportId.

        The endpoint is async: the reportId is created immediately, but
        the underlying job runs in the background. Caller must poll
        via `wait_report` for the metadata to reach DONE.
        """
        body = self._post(PATH_QUERIES_RUN, json_body={}, queryId=query_id)
        # Response shape: {"key": {"queryId": "...", "reportId": "..."}, ...}
        key = body.get("key") or {}
        report_id = key.get("reportId") or body.get("reportId")
        if not report_id:
            raise Dv360ReportingError(
                f"run_query response missing reportId (body keys={list(body)})"
            )
        return str(report_id)

    def wait_report(
        self,
        query_id: str,
        report_id: str,
        poll_interval: int = POLL_INTERVAL_SECONDS,
        timeout_seconds: int = POLL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Poll GET /queries/{id}/reports/{rid} until DONE; return metadata dict.

        Returns the parsed metadata. Raises Dv360ReportingError on
        FAILED/CANCELLED, or when the poll exceeds `timeout_seconds`.
        """
        state = _PollState(
            deadline=time.time() + timeout_seconds,
            interval=poll_interval,
        )
        while True:
            body = self._get_json(
                PATH_REPORT, queryId=query_id, reportId=report_id
            )
            meta = (body.get("metadata") or {})
            status = meta.get("status", {}).get("state") or meta.get("status")
            if status == "DONE":
                return body
            if status in ("FAILED", "CANCELLED"):
                raise Dv360ReportingError(
                    f"report {report_id} ended in state={status}: "
                    f"{(meta.get('status', {}).get('errorMessage') or '')[:300]}"
                )
            if state.expired():
                raise Dv360ReportingError(
                    f"report {report_id} did not reach DONE within "
                    f"{timeout_seconds}s (last status={status})"
                )
            time.sleep(state.interval)

    def fetch_csv(self, download_url: str) -> str:
        """GET the signed Cloud Storage URL; return raw CSV body as text."""
        # Cloud Storage signed URLs are publicly readable for the brief
        # TTL DV360 sets; we don't add the Authorization header here.
        resp = self._session.get(download_url, timeout=self._timeout)
        if resp.status_code != 200:
            raise Dv360ReportingError(
                f"GET {download_url} → http {resp.status_code}: {resp.text[:300]}"
            )
        return resp.text


# ---------------------------------------------------------------------------
# Query spec + CSV → TermMetric translation
# ---------------------------------------------------------------------------


def build_dimension_query_spec(
    advertiser_id: str,
    line_item_id: str,
    week_start: date,
    week_end: date,
    timezone_code: str = "Europe/Rome",
) -> dict[str, Any]:
    """Build a body for POST /queries that asks for one row per
    (dimension, value) across our canonical targeting families.
    """
    return {
        "metadata": {
            "title": f"deevai-li-{line_item_id}-{week_start.isoformat()}",
            "dataRange": {
                "range": "CUSTOM_DATES",
                "customStartDate": {
                    "year": week_start.year,
                    "month": week_start.month,
                    "day": week_start.day,
                },
                "customEndDate": {
                    "year": week_end.year,
                    "month": week_end.month,
                    "day": week_end.day,
                },
            },
            "format": "CSV",
            "sendNotification": False,
        },
        "params": {
            "type": "STANDARD",
            "groupBys": list(DV360_DIMENSION_MAP.values()),
            "metrics": [
                "METRIC_IMPRESSIONS",
                "METRIC_CLICKS",
                "METRIC_TOTAL_CONVERSIONS",
                "METRIC_MEDIA_COST_ADVERTISER",
            ],
            "filters": [
                {"type": "FILTER_ADVERTISER", "value": advertiser_id},
                {"type": "FILTER_LINE_ITEM", "value": line_item_id},
            ],
        },
        "schedule": {"frequency": "ONE_TIME"},
        "timezoneCode": timezone_code,
    }


def parse_csv(csv_text: str) -> list[dict[str, str]]:
    """Parse DV360 Reporting CSV into list of dicts keyed by header.

    DV360 CSVs ship a header row, data rows, a blank line, then a
    footer of summary stats. The footer rows can be **wider or shorter**
    than the header (extra commas, or "Grand Total" appearing in the
    middle of the row), so we pre-split on physical blank lines and
    only parse the leading data block.
    """
    # Split into the portion before the first blank line. Anything
    # after the blank line is footer/summary that we discard outright.
    lines: list[str] = []
    for raw in csv_text.splitlines():
        if raw.strip() == "":
            break
        lines.append(raw)
    if not lines:
        return []

    rows: list[dict[str, str]] = []
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    for row in reader:
        row.pop(None, None)
        # Defensive: drop rows whose values aren't simple strings
        cleaned: dict[str, str] = {}
        for k, v in row.items():
            if not isinstance(v, str):
                continue
            cleaned[(k or "").strip()] = v.strip()
        if not cleaned:
            continue
        # Footer guard: a "Grand Total" / "Report Date" string anywhere
        # in the row marks the boundary of the data block.
        joined = " ".join(cleaned.values()).lower()
        if "grand total" in joined or joined.startswith("report date"):
            break
        if any(cleaned.values()):
            rows.append(cleaned)
    return rows


def rows_to_metrics(rows: list[dict[str, str]]) -> list[TermMetric]:
    """Translate parsed CSV rows into canonical TermMetric objects.

    DV360 reporting rows carry all groupBy columns. We pick the
    canonical dimension based on whichever expected column is populated
    for the row. Rows that match no canonical dimension are skipped.
    """
    # Reverse map: DV360 column → (canonical module, key)
    reverse_dim: dict[str, tuple[str, str]] = {
        col: canon for canon, col in DV360_DIMENSION_MAP.items()
    }

    out: list[TermMetric] = []
    for r in rows:
        canonical: Optional[tuple[str, str]] = None
        value: Optional[str] = None
        label: Optional[str] = None
        for col, canon in reverse_dim.items():
            v = r.get(col, "")
            if v and v not in ("—", "-"):
                canonical = canon
                value = v
                # Friendly label column is `<COL>_NAME` when present
                label = r.get(f"{col}_NAME") or v
                break
        if not canonical or value is None:
            continue
        impressions = _to_int(r.get("METRIC_IMPRESSIONS"))
        clicks = _to_int(r.get("METRIC_CLICKS"))
        visits = _to_int(r.get("METRIC_TOTAL_CONVERSIONS"))
        spend = _to_float(r.get("METRIC_MEDIA_COST_ADVERTISER"))
        if impressions == 0 and clicks == 0 and visits == 0 and spend == 0.0:
            continue
        out.append(
            TermMetric(
                targeting_module=canonical[0],
                targeting_key=canonical[1],
                value=value,
                field_label=label or value,
                impressions=impressions,
                clicks=clicks,
                visits=visits,
                spend=spend,
            )
        )
    return out


def _to_int(s: Any) -> int:
    if s is None or s == "":
        return 0
    try:
        return int(str(s).replace(",", "").replace(".", ""))
    except (TypeError, ValueError):
        try:
            return int(float(s))
        except (TypeError, ValueError):
            return 0


def _to_float(s: Any) -> float:
    if s is None or s == "":
        return 0.0
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0
