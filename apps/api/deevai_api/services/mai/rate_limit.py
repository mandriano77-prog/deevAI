"""Rolling rate limit for POST /v1/mai/ask (per tenant_id)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

WINDOW_SECONDS = 60
MAX_REQUESTS = 30

_asks: dict[str, deque[float]] = defaultdict(deque)


def check_mai_ask_rate(tenant_id: str) -> None:
    now = time.monotonic()
    q = _asks[tenant_id]
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()
    if len(q) >= MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Troppe richieste M.AI per questo tenant: riprova tra un minuto.",
            headers={"Retry-After": "60"},
        )
    q.append(now)


def reset_mai_rate_limit_for_tests() -> None:
    _asks.clear()
