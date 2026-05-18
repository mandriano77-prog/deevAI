"""Integration tests for the DV360 OAuth flow endpoints.

We cover the three new routes without ever hitting Google:
  - POST /integrations/dv360/connect            (creates pending row)
  - GET  /integrations/dv360/callback           (mocked HTTP)
  - POST /integrations/{id}/dv360/select-advertiser (persists JSONB config)

The existing Amazon endpoints must continue to behave the same — that's
covered indirectly by the fact that we don't touch any Amazon code.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from deevai_api.models import Integration
from deevai_api.services import secrets_vault


@pytest.fixture(autouse=True)
def _force_fernet_vault(monkeypatch):
    """Force the local Fernet path in vault.

    The repo's `.env` has a malformed `KMS_KEY_ID` (whitespace + comment),
    which pydantic-settings reads as a non-empty string and tips the
    vault into KMS mode — then fails because no AWS creds are available
    in CI/local. We pin the dev path explicitly for these route tests.
    """
    monkeypatch.setattr(secrets_vault, "_use_kms", lambda: False)


# ---------------------------------------------------------------------------
# /dv360/connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dv360_connect_creates_pending_integration(api_client, db_session):
    client, tenant_id = api_client

    resp = await client.post(
        "/v1/integrations/dv360/connect",
        json={
            "name": "DV360 — Test Seat",
            "client_id": "google-oauth-client-id-XXXXXXXXXXXXX",
            "client_secret": "google-oauth-client-secret-XXXXXXXX",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["integration_id"]
    assert "accounts.google.com" in body["authorize_url"]
    assert "access_type=offline" in body["authorize_url"]
    assert "scope=" in body["authorize_url"]
    assert "display-video" in body["authorize_url"]

    # Row exists, status=pending, provider=dv360, secret encrypted
    row = await db_session.get(Integration, body["integration_id"])
    assert row is not None
    assert row.provider == "dv360"
    assert row.status == "pending"
    assert row.tenant_id == tenant_id
    # secret is encrypted at rest; the property round-trips it
    assert row.client_secret == "google-oauth-client-secret-XXXXXXXX"
    # raw ciphertext is NOT the plaintext
    assert row.client_secret_ciphertext is not None
    assert b"google-oauth-client-secret" not in row.client_secret_ciphertext


# ---------------------------------------------------------------------------
# /dv360/callback (mocked Google calls)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dv360_callback_completes_oauth_and_lists_advertisers(
    api_client, db_session, monkeypatch
):
    client, tenant_id = api_client

    # 1) Start the flow normally to get an integration_id + signed state
    resp = await client.post(
        "/v1/integrations/dv360/connect",
        json={
            "name": "DV360",
            "client_id": "cid-XXXXXXXXXX",
            "client_secret": "csec-XXXXXXXXXX",
        },
    )
    assert resp.status_code == 201
    integration_id = resp.json()["integration_id"]

    # The signed state is embedded in authorize_url; pull it out
    authorize_url = resp.json()["authorize_url"]
    state = [
        part.split("=", 1)[1]
        for part in authorize_url.split("?", 1)[1].split("&")
        if part.startswith("state=")
    ][0]

    # 2) Monkeypatch the two outbound HTTP services
    from deevai_api.services import dv360_advertisers, dv360_oauth

    async def fake_exchange(*, code, client_id, client_secret, redirect_uri=None):
        assert code == "fake-code"
        assert client_id == "cid-XXXXXXXXXX"
        return dv360_oauth.TokenExchangeResult(
            refresh_token="rtok-from-google",
            access_token="atok-from-google",
            expires_in=3600,
        )

    async def fake_list_advertisers(*, access_token, page_size=100, page_token=None):
        assert access_token == "atok-from-google"
        return [
            dv360_advertisers.Dv360Advertiser(
                advertiser_id="1234567890",
                display_name="Test Adv 1",
                partner_id="999",
                currency_code="EUR",
                timezone="Europe/Rome",
                entity_status="ENTITY_STATUS_ACTIVE",
            ),
            dv360_advertisers.Dv360Advertiser(
                advertiser_id="2222222222",
                display_name="Test Adv 2",
            ),
        ]

    monkeypatch.setattr(dv360_oauth, "exchange_code_for_tokens", fake_exchange)
    monkeypatch.setattr(dv360_advertisers, "list_advertisers", fake_list_advertisers)

    # 3) Hit the callback
    cb = await client.get(
        f"/v1/integrations/dv360/callback?code=fake-code&state={state}"
    )
    assert cb.status_code == 200, cb.text
    body = cb.json()
    assert body["integration_id"] == integration_id
    assert body["status"] == "connected"
    assert len(body["advertisers"]) == 2
    assert body["advertisers"][0]["advertiser_id"] == "1234567890"
    assert body["advertisers"][0]["currency_code"] == "EUR"

    # 4) Row should now carry status=connected and the refresh_token (encrypted)
    await db_session.commit()  # finalise from the route's transaction
    row = await db_session.get(Integration, integration_id)
    assert row.status == "connected"
    assert row.refresh_token == "rtok-from-google"
    assert row.last_error is None


@pytest.mark.asyncio
async def test_dv360_callback_rejects_user_denial(api_client):
    client, _ = api_client
    resp = await client.get(
        "/v1/integrations/dv360/callback?code=x&state=y&error=access_denied"
    )
    assert resp.status_code == 400
    assert "access_denied" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_dv360_callback_rejects_bad_state(api_client):
    client, _ = api_client
    resp = await client.get(
        "/v1/integrations/dv360/callback?code=x&state=tampered.token"
    )
    assert resp.status_code == 400
    assert "Invalid state" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /dv360/select-advertiser
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dv360_select_advertiser_persists_into_provider_config(
    api_client, db_session
):
    client, tenant_id = api_client

    # Seed a connected DV360 integration directly
    row = Integration(
        tenant_id=tenant_id,
        provider="dv360",
        name="DV360",
        client_id="cid",
        status="connected",
    )
    row.client_secret = "csec"
    row.refresh_token = "rtok"
    db_session.add(row)
    await db_session.flush()
    integration_id = row.id

    resp = await client.post(
        f"/v1/integrations/{integration_id}/dv360/select-advertiser",
        json={"advertiser_id": "1234567890", "partner_id": "999"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "dv360"
    assert body["provider_config"] == {
        "advertiser_id": "1234567890",
        "partner_id": "999",
    }

    # Re-read via a fresh query — the response body is the contract that
    # matters; the underlying SQLAlchemy session reuse + the JSONB
    # mutation can be sensitive to expire/refresh timing in tests.
    fetched = await db_session.get(Integration, integration_id)
    assert fetched is not None
    assert fetched.provider_config == {
        "advertiser_id": "1234567890",
        "partner_id": "999",
    }


@pytest.mark.asyncio
async def test_dv360_select_advertiser_rejects_wrong_provider(
    api_client, db_session
):
    client, tenant_id = api_client

    row = Integration(
        tenant_id=tenant_id,
        provider="amazon_dsp",
        name="Amazon",
        client_id="cid",
        status="connected",
    )
    row.client_secret = "csec"
    db_session.add(row)
    await db_session.flush()

    resp = await client.post(
        f"/v1/integrations/{row.id}/dv360/select-advertiser",
        json={"advertiser_id": "1234567890"},
    )
    assert resp.status_code == 400
    assert "not a DV360" in resp.json()["detail"]
