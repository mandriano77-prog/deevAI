"""Live HTTP layer tests for DV360 — auth + reporting + bid client.

We mock `requests.Session` with a minimal recorder. No real network
calls. The goal is to prove:

- The OAuth refresh_token exchange hits the right endpoint with the
  right form-encoded body and caches the access_token correctly.
- The reporting pipeline (create → run → wait → fetch CSV → parse)
  composes correctly and returns canonical TermMetric rows.
- The bid client list/bulkEdit endpoints carry the right URLs, headers,
  and JSON bodies.
- dry_run=True never issues a write request.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from bidagent.providers.dv360 import (
    Dv360BidProvider,
    Dv360MetricsProvider,
    Dv360ProviderCredentials,
)
from bidagent.providers.dv360.auth import (
    Dv360Auth,
    Dv360AuthError,
    Dv360Credentials,
    TOKEN_URL,
)
from bidagent.providers.dv360.bid_client import (
    DV360_API_BASE,
    Dv360BidClientError,
    Dv360LineItemClient,
)
from bidagent.providers.dv360.metrics_client import (
    REPORTING_BASE_URL,
    Dv360ReportingClient,
    Dv360ReportingConfig,
    Dv360ReportingError,
    parse_csv,
    rows_to_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status: int = 200,
    json_body: Optional[dict[str, Any]] = None,
    text: Optional[str] = None,
):
    """Build a MagicMock that quacks like a requests.Response."""
    m = MagicMock()
    m.status_code = status
    m.text = text if text is not None else json.dumps(json_body or {})
    if json_body is not None:
        m.json = MagicMock(return_value=json_body)
    elif text is not None:
        m.json = MagicMock(side_effect=ValueError("not json"))
    else:
        m.json = MagicMock(return_value={})
    return m


def _creds() -> Dv360ProviderCredentials:
    return Dv360ProviderCredentials(
        client_id="cid-test",
        client_secret="csec-test",
        refresh_token="rtok-test",
        advertiser_id="adv-999",
        partner_id="par-1",
    )


def _single_decision_plan():
    """Plan with one changed decision on a device-type term.

    Centralised so the dry-run and live-apply tests share the same fixture
    and stay in sync with the real `ModifierDecision` / `Plan` dataclasses.
    """
    from bidagent.models import (
        ActionReason,
        ModifierDecision,
        ModifierTerm,
        Plan,
    )

    term = ModifierTerm(
        targeting_module="device",
        targeting_key="device_type",
        value="MOBILE",
        modifier=1.0,
        field_label="Smartphone",
    )
    dec = ModifierDecision(
        term=term,
        previous_modifier=1.0,
        new_modifier=1.25,
        reason=ActionReason.UNDER_TARGET,
        observed_cpv=2.10,
        observed_impressions=10_000,
        observed_visits=40,
        note="cheap, bid up",
    )
    return Plan(
        line_item_id=111,
        line_item_name="t",
        cpv_target=2.5,
        blended_cpv_observed=3.0,
        blended_visits=40,
        blended_spend=120.0,
        decisions=[dec],
        week_label="w",
    )


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------


def test_auth_exchange_refresh_token_caches_access_token():
    session = MagicMock()
    session.post = MagicMock(
        return_value=_mock_response(
            200, {"access_token": "AT-1", "expires_in": 3600}
        )
    )
    creds = Dv360Credentials(
        client_id="cid", client_secret="csec", refresh_token="rtok"
    )
    auth = Dv360Auth(creds, session=session)

    token1 = auth.access_token()
    token2 = auth.access_token()

    assert token1 == "AT-1"
    assert token2 == "AT-1"
    # POST hit only once thanks to the cache
    assert session.post.call_count == 1
    args, kwargs = session.post.call_args
    assert args[0] == TOKEN_URL
    assert kwargs["data"]["grant_type"] == "refresh_token"
    assert kwargs["data"]["client_id"] == "cid"
    assert kwargs["data"]["refresh_token"] == "rtok"


def test_auth_raises_on_http_error():
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_response(401, text="nope"))
    creds = Dv360Credentials(client_id="c", client_secret="s", refresh_token="r")
    auth = Dv360Auth(creds, session=session)
    with pytest.raises(Dv360AuthError):
        auth.access_token()


def test_auth_invalidate_forces_re_exchange():
    session = MagicMock()
    session.post = MagicMock(
        return_value=_mock_response(
            200, {"access_token": "AT-X", "expires_in": 3600}
        )
    )
    creds = Dv360Credentials(client_id="c", client_secret="s", refresh_token="r")
    auth = Dv360Auth(creds, session=session)
    auth.access_token()
    auth.invalidate()
    auth.access_token()
    assert session.post.call_count == 2


# ---------------------------------------------------------------------------
# REPORTING — happy path
# ---------------------------------------------------------------------------


_SAMPLE_CSV = (
    "FILTER_SITE_DCM,FILTER_APP_ID,FILTER_DEVICE_TYPE,FILTER_COUNTRY,"
    "FILTER_REGION,FILTER_CITY,FILTER_AUDIENCE_LIST,"
    "METRIC_IMPRESSIONS,METRIC_CLICKS,METRIC_TOTAL_CONVERSIONS,"
    "METRIC_MEDIA_COST_ADVERTISER\n"
    "lastampa.it,,,,,,,180000,1800,720,1620.00\n"
    "repubblica.it,,,,,,,140000,1100,300,1980.00\n"
    ",,DEVICE_TYPE_SMART_PHONE,,,,,200000,2100,950,2375.00\n"
    "\n"
    ",,,,,,,Grand Total,,,,\n"
)


def test_reporting_pipeline_end_to_end_yields_term_metrics():
    """Mock a 4-call sequence (token → create → run → wait → csv).

    The reporting client uses the session for: token exchange (POST),
    create_query (POST), run_query (POST), wait_report (GET), fetch_csv
    (GET). We script them in order.
    """
    session = MagicMock()
    session.post = MagicMock(
        side_effect=[
            # 1) token exchange
            _mock_response(200, {"access_token": "AT", "expires_in": 3600}),
            # 2) create_query
            _mock_response(200, {"queryId": "q-42"}),
            # 3) run_query
            _mock_response(200, {"key": {"queryId": "q-42", "reportId": "r-7"}}),
        ]
    )
    session.get = MagicMock(
        side_effect=[
            # 4) wait_report — already DONE in first poll
            _mock_response(
                200,
                {
                    "metadata": {
                        "status": {"state": "DONE"},
                        "googleCloudStoragePath": "https://storage.example/r-7.csv",
                    }
                },
            ),
            # 5) fetch_csv
            _mock_response(200, text=_SAMPLE_CSV),
        ]
    )

    provider = Dv360MetricsProvider(_creds(), session=session)
    metrics = provider.fetch_week_metrics(
        line_item_external_id="li-1",
        week_start=date(2026, 5, 4),
        week_end=date(2026, 5, 10),
    )

    # 3 data rows in the sample CSV, all should map to canonical metrics
    assert len(metrics) == 3
    modules = {m.targeting_module for m in metrics}
    assert "inventory" in modules
    assert "device" in modules

    # Verify the URLs we hit
    posted_urls = [c.args[0] for c in session.post.call_args_list]
    assert posted_urls[0] == TOKEN_URL
    assert posted_urls[1] == REPORTING_BASE_URL + "/queries"
    assert posted_urls[2] == REPORTING_BASE_URL + "/queries/q-42:run"
    got_urls = [c.args[0] for c in session.get.call_args_list]
    assert got_urls[0] == REPORTING_BASE_URL + "/queries/q-42/reports/r-7"
    assert got_urls[1] == "https://storage.example/r-7.csv"


def test_reporting_wait_raises_on_failed_state():
    session = MagicMock()
    session.post = MagicMock(
        side_effect=[
            _mock_response(200, {"access_token": "AT", "expires_in": 3600}),
        ]
    )
    session.get = MagicMock(
        return_value=_mock_response(
            200,
            {
                "metadata": {
                    "status": {"state": "FAILED", "errorMessage": "boom"},
                }
            },
        )
    )
    cfg = Dv360ReportingConfig(partner_id="", advertiser_id="adv")
    auth = Dv360Auth(
        Dv360Credentials(client_id="c", client_secret="s", refresh_token="r"),
        session=session,
    )
    client = Dv360ReportingClient(auth, cfg, session=session)
    with pytest.raises(Dv360ReportingError) as exc:
        client.wait_report("q", "r", poll_interval=0, timeout_seconds=1)
    assert "FAILED" in str(exc.value)


def test_reporting_wait_times_out_when_stuck():
    session = MagicMock()
    session.post = MagicMock(
        side_effect=[_mock_response(200, {"access_token": "AT", "expires_in": 3600})]
    )
    # Always pending → triggers timeout
    session.get = MagicMock(
        return_value=_mock_response(
            200, {"metadata": {"status": {"state": "RUNNING"}}}
        )
    )
    cfg = Dv360ReportingConfig(partner_id="", advertiser_id="adv")
    auth = Dv360Auth(
        Dv360Credentials(client_id="c", client_secret="s", refresh_token="r"),
        session=session,
    )
    client = Dv360ReportingClient(auth, cfg, session=session)
    with pytest.raises(Dv360ReportingError) as exc:
        client.wait_report("q", "r", poll_interval=0, timeout_seconds=0)
    assert "did not reach DONE" in str(exc.value)


def test_csv_parser_skips_footer_and_empty_rows():
    rows = parse_csv(_SAMPLE_CSV)
    assert len(rows) == 3
    assert rows[0]["FILTER_SITE_DCM"] == "lastampa.it"
    metrics = rows_to_metrics(rows)
    assert len(metrics) == 3
    cpvs = sorted(m.cpv for m in metrics)
    # All three CPVs must be finite and positive
    assert all(c > 0 for c in cpvs)


# ---------------------------------------------------------------------------
# BID CLIENT — list + bulkEdit
# ---------------------------------------------------------------------------


def test_bid_provider_list_assigned_targeting_returns_canonical_modifiers():
    session = MagicMock()
    session.post = MagicMock(
        return_value=_mock_response(200, {"access_token": "AT", "expires_in": 3600})
    )
    # Each canonical targeting type triggers one GET. We respond with
    # a single assignedTargetingOption for the DEVICE_TYPE call and
    # empty for the others.
    def _get_side_effect(url, **_):
        if "TARGETING_TYPE_DEVICE_TYPE" in url:
            return _mock_response(
                200,
                {
                    "assignedTargetingOptions": [
                        {
                            "targetingType": "TARGETING_TYPE_DEVICE_TYPE",
                            "deviceTypeDetails": {
                                "targetingOptionId": "DEVICE_TYPE_SMART_PHONE",
                                "bidMultiplier": 1.4,
                                "displayName": "Smartphone",
                            },
                        }
                    ]
                },
            )
        return _mock_response(200, {"assignedTargetingOptions": []})

    session.get = MagicMock(side_effect=_get_side_effect)

    provider = Dv360BidProvider(_creds(), session=session)
    modifiers = provider.get_current_modifiers("li-1")

    assert any(
        m.targeting_module == "device"
        and m.targeting_key == "device_type"
        and m.value == "DEVICE_TYPE_SMART_PHONE"
        and m.modifier == 1.4
        for m in modifiers
    )


def test_bid_provider_apply_plan_dry_run_does_not_post():
    session = MagicMock()
    session.post = MagicMock(
        return_value=_mock_response(200, {"access_token": "AT", "expires_in": 3600})
    )
    provider = Dv360BidProvider(_creds(), session=session)

    # Build a minimal plan with one changed decision
    plan = _single_decision_plan()
    result = provider.apply_plan(plan, dry_run=True)
    assert result.ok and result.dry_run
    # Dry-run must short-circuit BEFORE any HTTP call. Not even the
    # OAuth token exchange should fire, because we never need a token
    # without an actual request to authenticate.
    assert session.post.call_count == 0
    assert session.get.call_count == 0


def test_bid_provider_apply_plan_live_posts_bulk_edit():
    session = MagicMock()
    session.post = MagicMock(
        side_effect=[
            _mock_response(200, {"access_token": "AT", "expires_in": 3600}),
            _mock_response(200, {"updatedLineItemIds": ["111"]}),
        ]
    )
    provider = Dv360BidProvider(_creds(), session=session)

    plan = _single_decision_plan()
    result = provider.apply_plan(plan, dry_run=False)
    assert result.ok and not result.dry_run
    # The second POST must be the bulkEdit endpoint
    last_post_url = session.post.call_args_list[-1].args[0]
    assert last_post_url.endswith(":bulkEditAssignedTargetingOptions")
    assert last_post_url.startswith(DV360_API_BASE)
    # And the body shape must include lineItemIds + createRequests
    body = session.post.call_args_list[-1].kwargs["json"]
    assert body["lineItemIds"] == ["111"]
    assert isinstance(body["createRequests"], list)
    assert len(body["createRequests"]) == 1
    assert (
        body["createRequests"][0]["targetingType"]
        == "TARGETING_TYPE_DEVICE_TYPE"
    )
