"""Push approved bid-modifier decisions to DV360 (live API).

Pipeline:
    Run → LineItem → Advertiser → Integration → Dv360Credentials
                                        │
                                        ▼
                              Dv360Auth + Dv360LineItemClient
                                        │
                                        ▼
                       bulkEditAssignedTargetingOptions

Behaviour:
- ``settings.dsp_dry_run=True`` (default): builds the DV360 payload, logs it,
  marks decisions as ``applied`` with ``application_error="[dry-run]"``,
  and returns ``ok=True`` without contacting Google.
- ``settings.dsp_dry_run=False``: instantiates the live client and POSTs
  ``advertisers.lineItems:bulkEditAssignedTargetingOptions``. Decisions are
  marked ``applied`` on success or ``failed_to_apply`` on error, with the
  HTTP status / transport error captured in ``Decision.application_error``.

Decisions whose targeting (module, key) DV360 doesn't support are silently
skipped at translation time inside ``build_bulk_edit_body`` — they remain
``approved`` (not applied) so the operator can see the gap in the digest.

Tech debt accepted in v1:
- ``LineItem.amazon_line_item_id`` is reused as the DV360 lineItemId.
  Column rename to ``provider_line_item_id`` is planned in v2.
- ``Advertiser.amazon_advertiser_id`` is reused as the DV360 advertiserId
  fallback when ``Integration.provider_config['advertiser_id']`` is unset.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bidagent.models import (
    ActionReason,
    ModifierDecision,
    ModifierTerm,
    Plan,
)
from bidagent.providers.dv360.auth import (
    Dv360Auth,
    Dv360AuthError,
    Dv360Credentials,
)
from bidagent.providers.dv360.bid_client import (
    Dv360LineItemClient,
    build_bulk_edit_body,
)

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

    Same shape as the Decision is provider-agnostic because the term fields
    (targeting_module, targeting_key, value) already match the DV360
    vocabulary (deviceType, geoRegion, …).
    """
    out: list[ModifierTerm] = []
    for d in decisions:
        out.append(
            ModifierTerm(
                targeting_module=d.targeting_module,
                targeting_key=d.targeting_key,
                value=d.value,
                modifier=float(d.new_modifier),
                field_label=d.field_label or "",
            )
        )
    return out


def decisions_to_plan(
    line_item: LineItem,
    run: Run,
    decisions: list[Decision],
) -> Plan:
    """Build a bidagent ``Plan`` from DB rows so we can reuse
    ``build_bulk_edit_body(plan)`` from the provider package.
    """
    modifier_decisions: list[ModifierDecision] = []
    for d in decisions:
        term = ModifierTerm(
            targeting_module=d.targeting_module,
            targeting_key=d.targeting_key,
            value=d.value,
            modifier=float(d.new_modifier),
            field_label=d.field_label or "",
        )
        modifier_decisions.append(
            ModifierDecision(
                term=term,
                previous_modifier=float(d.previous_modifier),
                new_modifier=float(d.new_modifier),
                reason=ActionReason(d.reason)
                if d.reason in {r.value for r in ActionReason}
                else ActionReason.ON_TARGET,
                observed_cpv=float(d.observed_cpv or 0.0),
                observed_impressions=int(d.observed_impressions or 0),
                observed_visits=int(d.observed_visits or 0),
                note=d.note or "",
            )
        )

    return Plan(
        # NOTE: bidagent Plan expects int line_item_id; we pass the DV360
        # numeric ID stored in LineItem.amazon_line_item_id (string column,
        # holds the DV360 lineItemId integer in our schema).
        line_item_id=int(line_item.amazon_line_item_id),
        line_item_name=line_item.name,
        cpv_target=float(line_item.cpv_target),
        blended_cpv_observed=float(run.blended_cpv_observed or 0.0),
        blended_visits=int(run.blended_visits or 0),
        blended_spend=float(run.blended_spend or 0.0),
        decisions=modifier_decisions,
        week_label=run.week_label,
    )


def _credentials_from_integration(integration: Integration) -> Dv360Credentials:
    """Decrypt + assemble the OAuth credentials we hand to ``Dv360Auth``."""
    client_id = integration.client_id
    client_secret = integration.client_secret  # property: decrypts on access
    refresh_token = integration.refresh_token  # property: decrypts on access
    if not (client_id and client_secret and refresh_token):
        raise DspApplyError(
            "Integration missing OAuth credentials — reconnect DV360"
        )
    return Dv360Credentials(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )


def _advertiser_id_from_integration(
    integration: Integration,
    advertiser: Advertiser,
) -> str:
    """DV360 advertiserId. Prefer Integration.provider_config['advertiser_id']
    (set during onboarding) and fall back to Advertiser.amazon_advertiser_id."""
    cfg = integration.provider_config or {}
    aid = cfg.get("advertiser_id") if isinstance(cfg, dict) else None
    return str(aid or advertiser.amazon_advertiser_id)


async def apply_run_to_dsp(
    *,
    run: Run,
    db: AsyncSession,
) -> dict:
    """Apply the approved decisions of a Run to DV360.

    Returns a dict with ``ok``, ``dry_run``, ``applied`` (count), and either
    a ``note`` (dry-run) or ``error`` (live failure). On live failure the
    Decision rows are individually marked ``failed_to_apply`` with the HTTP
    detail captured in ``application_error``.
    """
    settings = get_settings()

    # 1) Hydrate the graph: LineItem → Advertiser → Integration.
    line_item = await db.scalar(
        select(LineItem).where(LineItem.id == run.line_item_id)
    )
    if line_item is None:
        raise DspApplyError(f"LineItem {run.line_item_id} not found")

    advertiser = await db.scalar(
        select(Advertiser).where(Advertiser.id == line_item.advertiser_id)
    )
    if advertiser is None:
        raise DspApplyError(
            f"Advertiser {line_item.advertiser_id} not found"
        )

    integration = await db.scalar(
        select(Integration).where(Integration.id == advertiser.integration_id)
    )
    if integration is None:
        raise DspApplyError(
            f"Integration {advertiser.integration_id} not found — "
            "tenant has no DV360 connection"
        )

    # 2) Load only approved decisions for this run (proposed/rejected stay out).
    result = await db.execute(
        select(Decision).where(
            Decision.run_id == run.id,
            Decision.status == "approved",
        )
    )
    approved = list(result.scalars().all())

    if not approved:
        log.info("dsp_apply run_id=%s no approved decisions, skipping", run.id)
        return {
            "ok": True,
            "dry_run": settings.dsp_dry_run,
            "applied": 0,
            "note": "no approved decisions to apply",
        }

    # 3) Build the DV360 payload via the provider package (single source of truth).
    plan = decisions_to_plan(line_item, run, approved)
    body = build_bulk_edit_body(plan)

    # If translation dropped every decision (unsupported targeting types),
    # we treat it as "nothing to do" rather than a failure.
    n_create = len(body.get("createRequests", []))
    if n_create == 0:
        log.warning(
            "dsp_apply run_id=%s all %d decisions had unsupported DV360 targeting types",
            run.id,
            len(approved),
        )
        return {
            "ok": True,
            "dry_run": settings.dsp_dry_run,
            "applied": 0,
            "note": (
                f"all {len(approved)} approved decisions targeted DV360-"
                "unsupported terms; nothing to send"
            ),
        }

    advertiser_id = _advertiser_id_from_integration(integration, advertiser)

    # 4) Dry-run short-circuit: log + mark decisions applied, no HTTP.
    if settings.dsp_dry_run:
        log.info(
            "dsp_apply DRY-RUN run_id=%s advertiserId=%s lineItemId=%s "
            "createRequests=%d",
            run.id,
            advertiser_id,
            plan.line_item_id,
            n_create,
        )
        now = _utcnow()
        for d in approved:
            d.status = "applied"
            d.applied_at = now
            d.application_error = "[dry-run]"
        run.n_changes_applied = (run.n_changes_applied or 0) + len(approved)
        await db.flush()
        return {
            "ok": True,
            "dry_run": True,
            "applied": len(approved),
            "note": (
                f"[dry-run] would POST {n_create} create-requests to "
                f"advertisers/{advertiser_id}/lineItems:bulkEdit"
            ),
        }

    # 5) Live path — assemble auth + client, fire the bulkEdit.
    try:
        creds = _credentials_from_integration(integration)
        auth = Dv360Auth(creds)
        client = Dv360LineItemClient(auth=auth, dry_run=False)
        api_result = client.bulk_edit_targeting(advertiser_id, body)
    except (Dv360AuthError, DspApplyError) as exc:
        log.error(
            "dsp_apply run_id=%s auth/setup failure: %s", run.id, exc
        )
        now = _utcnow()
        for d in approved:
            d.status = "failed_to_apply"
            d.application_error = f"auth: {exc}"[:500]
        await db.flush()
        return {
            "ok": False,
            "dry_run": False,
            "applied": 0,
            "error": str(exc),
        }

    # 6) Persist outcome on every Decision row (one DB roundtrip via flush).
    now = _utcnow()
    if api_result.ok:
        for d in approved:
            d.status = "applied"
            d.applied_at = now
            d.application_error = None
        run.n_changes_applied = (run.n_changes_applied or 0) + len(approved)
    else:
        err = api_result.note or f"http {api_result.status_code}"
        for d in approved:
            d.status = "failed_to_apply"
            d.application_error = err[:500]

    await db.flush()

    return {
        "ok": api_result.ok,
        "dry_run": False,
        "applied": len(approved) if api_result.ok else 0,
        "status_code": api_result.status_code,
        "note": api_result.note,
    }
