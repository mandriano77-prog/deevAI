"""Google DV360 OAuth flow (user-consent / refresh_token).

Two endpoints from Google:

  - Authorize: https://accounts.google.com/o/oauth2/v2/auth
  - Token:     https://oauth2.googleapis.com/token

We request the offline-access refresh_token so deevAI can keep
managing the tenant's DV360 without re-prompting them.

Scopes we ask for:
  - https://www.googleapis.com/auth/display-video       (line items, bid mults)
  - https://www.googleapis.com/auth/doubleclickbidmanager (reporting API)

Reference:
  https://developers.google.com/identity/protocols/oauth2/web-server
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

OAUTH_SCOPES = " ".join(
    [
        "https://www.googleapis.com/auth/display-video",
        "https://www.googleapis.com/auth/doubleclickbidmanager",
    ]
)


@dataclass
class TokenExchangeResult:
    """Token bundle from Google."""

    refresh_token: str
    access_token: str
    expires_in: int


def build_authorize_url(
    *,
    client_id: str,
    state: str,
    redirect_uri: str | None = None,
) -> str:
    """Build the Google OAuth consent URL the user clicks.

    We force `access_type=offline` (otherwise no refresh_token) and
    `prompt=consent` so the user re-grants if they revoked previously.
    """
    settings = get_settings()
    params = {
        "client_id": client_id,
        "scope": OAUTH_SCOPES,
        "response_type": "code",
        "redirect_uri": redirect_uri or settings.dv360_redirect_uri,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str | None = None,
) -> TokenExchangeResult:
    """Trade an authorization `code` for refresh + access tokens.

    Errors are raised loudly. Google's token endpoint is well-behaved
    but the error bodies are short — we surface up to 200 chars so the
    UI can show the user something useful.
    """
    settings = get_settings()
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri or settings.dv360_redirect_uri,
    }

    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(TOKEN_URL, data=body)

    if resp.status_code != 200:
        log.error("DV360 token exchange failed: %s %s", resp.status_code, resp.text[:200])
        raise RuntimeError(
            f"DV360 token exchange failed ({resp.status_code}). "
            "Verify the OAuth client_id / client_secret / redirect_uri "
            "match the credentials in Google Cloud Console."
        )

    data = resp.json()
    if "refresh_token" not in data:
        # Most common cause: app type isn't 'Web' or the user already
        # consented and Google didn't re-issue a refresh_token. The
        # `prompt=consent` in the authorize URL prevents this in normal
        # flows, but we surface the case to make debugging easy.
        raise RuntimeError(
            "DV360 token response missing refresh_token. Most likely "
            "the OAuth client is misconfigured, or access_type=offline "
            "wasn't honoured. Re-create the consent."
        )

    return TokenExchangeResult(
        refresh_token=data["refresh_token"],
        access_token=data["access_token"],
        expires_in=int(data.get("expires_in", 3600)),
    )


async def refresh_access_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> TokenExchangeResult:
    """Trade a stored refresh_token for a fresh access_token at runtime.

    Google refresh_tokens typically do not get rotated, so we keep the
    stored one as the canonical credential.
    """
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(TOKEN_URL, data=body)

    if resp.status_code != 200:
        log.error("DV360 access-token refresh failed: %s", resp.status_code)
        raise RuntimeError(f"DV360 token refresh failed ({resp.status_code})")

    data = resp.json()
    return TokenExchangeResult(
        refresh_token=data.get("refresh_token", refresh_token),
        access_token=data["access_token"],
        expires_in=int(data.get("expires_in", 3600)),
    )
