"""List DV360 advertisers visible under a freshly authorised token.

In DV360 the hierarchy is Partner → Advertiser → Campaign → Insertion
Order → Line Item. A refresh_token granted by a Google user can give
access to many advertisers across one or more partners; we list them
all and let the operator pick which ones DeevAI should manage.

Endpoint: GET /v4/advertisers (paginated)

Reference:
  https://developers.google.com/display-video/api/reference/rest/v4/advertisers/list
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger(__name__)

DV360_API_BASE = "https://displayvideo.googleapis.com/v4"


@dataclass
class Dv360Advertiser:
    advertiser_id: str
    display_name: str
    partner_id: Optional[str] = None
    entity_status: Optional[str] = None
    currency_code: Optional[str] = None
    timezone: Optional[str] = None


async def list_advertisers(
    *,
    access_token: str,
    page_size: int = 100,
    page_token: Optional[str] = None,
) -> list[Dv360Advertiser]:
    """GET /v4/advertisers — list all advertisers the access_token can see.

    Walks all pages. DV360 caps the page size at 200; we ask for 100 to
    stay comfortable. Most tenants will have 1-5 advertisers; we still
    walk pagination defensively for agency seats.
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    out: list[Dv360Advertiser] = []
    next_token: Optional[str] = page_token
    safety_limit = 20  # at 100/page that's 2000 advertisers; plenty
    iterations = 0

    async with httpx.AsyncClient(timeout=15.0) as http:
        while True:
            iterations += 1
            if iterations > safety_limit:
                log.warning("DV360 list_advertisers stopped after %s pages", safety_limit)
                break
            params: dict[str, str] = {"pageSize": str(page_size)}
            if next_token:
                params["pageToken"] = next_token
            resp = await http.get(
                f"{DV360_API_BASE}/advertisers",
                headers=headers,
                params=params,
            )
            if resp.status_code != 200:
                log.error(
                    "DV360 advertisers fetch failed: %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
                raise RuntimeError(
                    f"DV360 /v4/advertisers returned {resp.status_code}. "
                    "Most likely the OAuth scope is missing display-video, "
                    "or this Google account has no DV360 access."
                )

            data = resp.json() or {}
            for a in data.get("advertisers", []) or []:
                ad_id = a.get("advertiserId")
                if not ad_id:
                    continue
                gen = a.get("generalConfig") or {}
                out.append(
                    Dv360Advertiser(
                        advertiser_id=str(ad_id),
                        display_name=str(a.get("displayName") or ad_id),
                        partner_id=(str(a["partnerId"]) if a.get("partnerId") else None),
                        entity_status=a.get("entityStatus"),
                        currency_code=gen.get("currencyCode"),
                        timezone=gen.get("timeZone"),
                    )
                )

            next_token = data.get("nextPageToken")
            if not next_token:
                break
    return out
