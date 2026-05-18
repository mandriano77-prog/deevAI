"""Cryptographic helpers — HMAC-signed state tokens for the OAuth flow.

The OAuth `state` parameter must be unpredictable, integrity-protected,
and tied to the request that started the flow. We pack a small JSON
payload (integration_id + nonce + expiry) and HMAC-sign it with
`API_SECRET_KEY`. Anything that comes back from Amazon and doesn't
verify or has expired is rejected."""

from __future__ import annotations

import base64
import hmac
import json
import secrets
import time
from hashlib import sha256

from ..config import get_settings

STATE_TTL_SECONDS = 600   # 10 minutes — generous for users to consent on Amazon


def _key() -> bytes:
    return get_settings().api_secret_key.encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def sign_state(integration_id: str) -> str:
    """Produce a tamper-proof state token for an OAuth flow.

    Layout: base64url(payload).base64url(hmac256(payload))
    Payload: {"i": <integration_id>, "n": <nonce>, "e": <expires_at>}"""

    payload = {
        "i": integration_id,
        "n": secrets.token_urlsafe(12),
        "e": int(time.time()) + STATE_TTL_SECONDS,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    mac = hmac.new(_key(), payload_bytes, sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(mac)}"


def verify_state(state: str) -> str:
    """Verify a state token. Returns the integration_id on success.
    Raises ValueError on any failure (tamper, expiry, malformed)."""

    try:
        payload_b64, mac_b64 = state.split(".", 1)
    except ValueError as e:
        raise ValueError("Malformed state token") from e

    payload_bytes = _b64url_decode(payload_b64)
    expected_mac = hmac.new(_key(), payload_bytes, sha256).digest()
    provided_mac = _b64url_decode(mac_b64)

    if not hmac.compare_digest(expected_mac, provided_mac):
        raise ValueError("State signature mismatch")

    payload = json.loads(payload_bytes.decode("utf-8"))
    if payload.get("e", 0) < time.time():
        raise ValueError("State token expired")

    integration_id = payload.get("i")
    if not integration_id:
        raise ValueError("State payload missing integration_id")
    return integration_id
