"""Push approved bid-modifier decisions to DV360 (live API).

⚠️ STATUS: STUB — the public surface (function signatures, exception
class, helper utilities) is preserved so that routers/scheduler can
import without changes, but the live execution path raises NotImplemented
until the DV360-native apply pipeline lands (planned as "pezzo 5":
wiring `bidagent.providers.dv360.bid_client` into this orchestrator).

What DOES still work here:
- ``is_observation_only`` — pure logic, unchanged (provider-agnostic helper).
- ``decisions_to_modifier_terms`` — pure transform, unchanged.
- ``DspApplyError`` — exception class for routers to catch.

What does NOT work yet:
- ``apply_run_to_dsp`` — the orchestrator. Raises NotImplementedError if
  ``dsp_dry_run=False``. In dry-run it logs the payload and returns ok=True,
  same observable behaviour as before but the payload is constructed for
  DV360, not Amazon DSP.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bidagent.models import ModifierTerm

from ..config import get_settings
from ..models import Advertiser, Decision, Integration, LineItem, Run, Setting

log = logging.getLogger(__name__)


class DspApplyError(Exception):
    """User-visible apply failure (missing config, observation window, etc.)."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_observation_only(
    line_item: LineItem,
    setting: Setting | None,
) -> tuple[bool, str]:
    """Decide whether this line item is currently in observation-only mode."""
    if line_item.mode == "observation_only":
        return True, "Line item is in observation-only mode"
    if setting and setting.observation_only_until:
        if _utcnow() < setting.observation_only_until:
            return True, "Tenant is still in the 14-day observation-only window"
    return False, ""


def decisions_to_modifier_terms(decisions: list[Decision]) -> list[ModifierTerm]:
    """Transform persisted Decision rows into the ModifierTerm shape the
    bidagent (and DV360 bid client) expects.

    Same shape as the Decision is provider-agnostic
    because the term fields (targeting_module, targeting_key, value)
    already match the DV360 vocabulary (deviceType, geoRegion, …).
    """
    out: list[ModifierTerm] = []
    for d in decisions:
        out.append(
            ModifierTerm(
                targeting_module=d.targeting_module,
                targeting_key=d.targeting_key,
                value=d.value,
                proposed_modifier=d.new_modifier,
            )
        )
    return out


async def apply_run_to_dsp(
    *,
    run: Run,
    db: AsyncSession,
) -> dict:
    """Apply the decisions of a Run to DV360.

    STUB BEHAVIOUR:
    - dry_run=True (default): logs the proposed payload, returns success
      so the scheduler / UI flow keeps working end-to-end.
    - dry_run=False: raises NotImplementedError, deliberately, until the
      DV360 apply pipeline lands.
    """
    settings = get_settings()

    # Load the related decisions in a single query — single round-trip.
    result = await db.execute(
        select(Decision).where(Decision.run_id == run.id)
    )
    decisions = list(result.scalars().all())

    terms = decisions_to_modifier_terms(decisions)

    if settings.dsp_dry_run:
        log.info(
            "dsp_apply DRY-RUN run_id=%s decisions=%d (DV360 apply STUB)",
            run.id,
            len(terms),
        )
        return {
            "ok": True,
            "dry_run": True,
            "applied": 0,
            "note": "DV360 apply path stubbed — set DSP_DRY_RUN=false to wire it (pezzo 5)",
        }

    raise NotImplementedError(
        "Live DV360 apply is not wired yet. Keep DSP_DRY_RUN=true until the "
        "DV360 bid_client orchestrator lands (planned: pezzo 5)."
    )
