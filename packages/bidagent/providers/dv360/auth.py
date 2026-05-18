"""OAuth user-consent authentication for Google DV360 + Bid Manager.

Flow (Google OAuth user-consent):

  1. Once, you create an OAuth client at https://console.cloud.google.com
     → APIs & Services → Credentials → "OAuth client ID" (type: Web).
     This gives you `client_id` + `client_secret`.
  2. Once per tenant, the user goes through the consent screen with the
     required scopes; we receive an authorization code and exchange it
     for a long-lived `refresh_token`. (That part lives in the API
     layer — `services/providers/dv360_oauth.py`.)
  3. At runtime, this module trades the `refresh_token` for a short-lived
     `access_token` (TTL ~3600s) and caches it.

We deliberately avoid taking `google-auth` as a dependency: the OAuth
refresh_token flow is a plain HTTP POST and matches the shape of the
Same shape across providers — swap implementation, not orchestration.

Service-account auth (the alternative) is intentionally out of scope of
this revision. We'll add it as a follow-up when (and if) an enterprise
tenant requests it.

Reference:
  https://developers.google.com/identity/protocols/oauth2/web-server#offline
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Optional

import requests

log = logging.getLogger(__name__)

# Standard Google token endpoint
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Scopes we need
SCOPE_DV360 = "https://www.googleapis.com/auth/display-video"
SCOPE_BID_MANAGER = "https://www.googleapis.com/auth/doubleclickbidmanager"

# Safety buffer: refresh ~5 min early
TOKEN_REFRESH_SAFETY_SECONDS = 300


class Dv360AuthError(RuntimeError):
    """Raised when token exchange fails. Carries provider-side detail."""


@dataclass
class Dv360Credentials:
    """OAuth credentials for talking to DV360 + Bid Manager.

    All three fields are required. They must come from a secret store
    (Secrets Manager, env var, .env in dev). Never check them into git.
    """

    client_id: str
    client_secret: str
    refresh_token: str


class AccessTokenCache:
    """Thread-safe cache of (access_token, expires_at).

    Token cache so the providers
    behave identically under concurrent use.
    """

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = Lock()

    def get(self) -> Optional[str]:
        with self._lock:
            if self._token and time.time() < self._expires_at:
                return self._token
            return None

    def put(self, token: str, ttl_seconds: int) -> None:
        with self._lock:
            self._token = token
            self._expires_at = time.time() + max(
                0, ttl_seconds - TOKEN_REFRESH_SAFETY_SECONDS
            )

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
            self._expires_at = 0.0


class Dv360Auth:
    """Refresh-token-based token manager.

    The `session` argument lets callers inject a pre-configured
    `requests.Session` (with retries, timeouts, proxy, etc.) and lets
    tests substitute a mock session that records the requests issued.
    """

    def __init__(
        self,
        creds: Dv360Credentials,
        session: Optional[requests.Session] = None,
        timeout_seconds: int = 15,
    ) -> None:
        if not (creds.client_id and creds.client_secret and creds.refresh_token):
            raise ValueError(
                "Dv360Credentials must supply client_id, client_secret, refresh_token."
            )
        self._creds = creds
        self._cache = AccessTokenCache()
        self._session = session or requests.Session()
        self._timeout = timeout_seconds

    # ------------------------------------------------------------------ HTTP

    def _exchange_refresh_token(self) -> tuple[str, int]:
        """POST to oauth2.googleapis.com/token; return (access_token, ttl).

        Raises:
            Dv360AuthError: when the exchange fails. We wrap the
                underlying detail to keep call sites provider-agnostic.
        """
        try:
            resp = self._session.post(
                TOKEN_URL,
                data={
                    "client_id": self._creds.client_id,
                    "client_secret": self._creds.client_secret,
                    "refresh_token": self._creds.refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise Dv360AuthError(f"transport error talking to Google: {exc}") from exc

        if resp.status_code != 200:
            raise Dv360AuthError(
                f"google token endpoint returned http {resp.status_code}: "
                f"{resp.text[:300]}"
            )
        try:
            body: dict[str, Any] = resp.json()
        except ValueError as exc:
            raise Dv360AuthError(f"non-JSON response from google token endpoint") from exc

        access_token = body.get("access_token")
        ttl = int(body.get("expires_in", 3600))
        if not access_token:
            raise Dv360AuthError(
                f"google token response missing access_token (keys={list(body)})"
            )
        return access_token, ttl

    # ----------------------------------------------------------------- public

    def access_token(self) -> str:
        cached = self._cache.get()
        if cached:
            return cached
        token, ttl = self._exchange_refresh_token()
        self._cache.put(token, ttl)
        return token

    def headers(self, content_type: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token()}",
            "Content-Type": content_type,
            "Accept": "application/json",
        }

    def invalidate(self) -> None:
        """Drop the cached access token. The next call refreshes."""
        self._cache.invalidate()
