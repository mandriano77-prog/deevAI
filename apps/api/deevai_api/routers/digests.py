"""Digest endpoints — generate the weekly narrative for a run.

For Sprint 2.4 we expose a single endpoint that runs the digest generator
either on a stored Run (looking it up by id) or on a synthetic Plan
(for the dashboard "Regenerate digest" button when there is no real
data yet).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import sys
from pathlib import Path

# Allow `from bidagent import ...` even though bidagent lives at packages/bidagent
_BIDAGENT_PATH = Path(__file__).resolve().parents[3] / "packages"
if str(_BIDAGENT_PATH) not in sys.path:
    sys.path.insert(0, str(_BIDAGENT_PATH))

from bidagent.decision_engine import build_plan  # noqa: E402
from bidagent.digest_generator import (  # noqa: E402
    DigestConfig,
    generate_digest,
)
from bidagent.providers.dv360.mock_data import (  # noqa: E402
    fake_dv360_week_metrics,
    fake_current_bid_multipliers,
    fake_runs_since_zeroed,
)
from bidagent.models import HygieneRules, OptimizerConfig, utcnow  # noqa: E402

from ..db import get_session  # noqa: E402
from ..deps import get_current_tenant_id  # noqa: E402
from ..schemas.digest import DigestGenerateRequest, DigestResponse  # noqa: E402

log = logging.getLogger(__name__)
router = APIRouter(prefix="/digests", tags=["digests"])


@router.post("/generate", response_model=DigestResponse)
async def generate_digest_endpoint(
    payload: Annotated[DigestGenerateRequest, Body()],
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> DigestResponse:
    """Generate a weekly digest.

    MVP behavior:
      - If `run_id` is None, we synthesize a Plan from mock data and run
        the generator on it. Useful for the dashboard demo before AMC is
        connected.
      - Once Sprint 2.5 lands, we look up the Run and reuse its `digest_text`
        if already cached.
    """
    # ── Synthetic path (no run_id) ─────────────────────────────────
    if payload.run_id is None:
        cfg = OptimizerConfig(cpv_target=0.40)
        hygiene = HygieneRules()
        metrics = fake_dv360_week_metrics()
        current_mods = fake_current_bid_multipliers(metrics)
        plan = build_plan(
            line_item_id=900_001,
            line_item_name="Brand Amico — Display+Native IT (mock)",
            week_label="4–10 maggio",
            metrics=metrics,
            current_modifiers=current_mods,
            runs_since_zeroed=fake_runs_since_zeroed(),
            current_max_bid=4.50,
            cfg=cfg,
            hygiene=hygiene,
        )

        digest_cfg = DigestConfig.from_env()
        digest_cfg.language = payload.language
        provider = _resolve_provider(digest_cfg)

        text = generate_digest(
            plan,
            previous_week_cpv=payload.previous_week_cpv,
            previous_week_visits=payload.previous_week_visits,
            config=digest_cfg,
        )

        return DigestResponse(
            run_id=None,
            week_label=plan.week_label,
            language=payload.language,
            text=text,
            generated_at=utcnow(),
            provider=provider,
            cached=False,
        )

    # ── Real run path (Sprint 2.5+) ────────────────────────────────
    # When Run model has actual data, look it up and regenerate (or return
    # cached digest_text from the Run row).
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Per ora generiamo solo digest sintetici. Connesso a runs reali nello Sprint 2.5.",
    )


def _resolve_provider(cfg: DigestConfig) -> str:
    if cfg.anthropic_api_key:
        return "anthropic"
    if cfg.openai_api_key:
        return "openai"
    return "template"
