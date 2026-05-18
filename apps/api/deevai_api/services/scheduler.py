"""Weekly scheduler — orchestrates the bidagent run per tenant.

Two ways the agent runs:
  1. Manual trigger (via POST /v1/runs/trigger) — for testing or
     "regenerate this week's plan now" UX.
  2. Cron — once a week, Sunday 23:00 CET. In dev we use FastAPI's
     background tasks plus a simple in-process timer. In production
     we hand this off to AWS EventBridge → Lambda (or GitHub Actions
     scheduled workflow) — see infra/terraform/scheduler.tf.

For each (Tenant × LineItem) that's `active` and has a connected
Integration:
  1. Pull last 14 days of performance from AMC → TermMetric[]
  2. Pull current bid adjustments from DSP API → current_modifiers
  3. Run decision_engine.build_plan(...) → Plan
  4. Persist Run + Decision rows
  5. Generate digest via digest_generator.generate_digest(plan)
  6. Save digest text on the Run row
  7. If line_item.mode == "auto_apply" and the tenant is past the
     observation-only window → call DSP API to push the new modifiers.
     Otherwise: leave decisions in "proposed" state for human approval.

This module is SAFE TO IMPORT but does not do I/O on import — all the
work happens inside `run_for_line_item()`. AMC + DSP calls are stubbed
for MVP (return mock data) — Sprint 3 wires them to the real adapters
in packages/bidagent/amazon/.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Allow bidagent imports
_BIDAGENT_PATH = Path(__file__).resolve().parents[3] / "packages"
if str(_BIDAGENT_PATH) not in sys.path:
    sys.path.insert(0, str(_BIDAGENT_PATH))

from bidagent.providers.dv360.mock_data import (  # noqa: E402
    fake_dv360_week_metrics,
    fake_current_bid_multipliers,
    fake_runs_since_zeroed,
    filter_supported_metrics,
)
from bidagent.digest_generator import DigestConfig, generate_digest  # noqa: E402

from ..models import Decision, LineItem, Run, Setting, Tenant  # noqa: E402
from .actions import get_action_funnel  # noqa: E402
from .bidagent_runtime import build_line_item_plan, compute_blended_roas  # noqa: E402
from .dsp_apply import DspApplyError, apply_run_to_dsp, is_observation_only  # noqa: E402

log = logging.getLogger(__name__)


async def run_for_line_item(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    digest_language: str = "it",
) -> Run:
    """Run one full pass of the bidagent on a single LineItem.

    Creates a Run row, all related Decision rows, generates the digest,
    and returns the persisted Run. Does NOT push changes to the DSP API
    — that happens in `apply_approved_decisions()` after human approval.
    """
    # 1. Load the line item and tenant settings
    line_item = await db.get(LineItem, line_item_id)
    if line_item is None or line_item.tenant_id != tenant_id:
        raise ValueError(f"LineItem {line_item_id} not found for tenant")

    setting_row = await db.execute(
        select(Setting).where(Setting.tenant_id == tenant_id).limit(1)
    )
    setting = setting_row.scalar_one_or_none()

    # 2. Pull data from AMC + DSP. STUBBED for MVP — Sprint 3 wires the real ones.
    metrics = filter_supported_metrics(fake_dv360_week_metrics())
    current_modifiers = fake_current_bid_multipliers(metrics)
    runs_since_zeroed = fake_runs_since_zeroed()
    current_max_bid = float(line_item.current_max_bid or 5.0)

    # 4. Run the decision engine
    now = datetime.now(timezone.utc)
    window_end = now
    window_start = now - timedelta(days=14)
    week_label = (
        f"{window_start.date().isoformat()} → {window_end.date().isoformat()}"
    )
    plan = await build_line_item_plan(
        db,
        tenant_id=tenant_id,
        line_item=line_item,
        setting=setting,
        metrics=metrics,
        current_modifiers=current_modifiers,
        runs_since_zeroed=runs_since_zeroed,
        current_max_bid=current_max_bid,
        week_label=week_label,
    )

    funnel_actions = await get_action_funnel(db, tenant_id=tenant_id)
    blended_roas = compute_blended_roas(
        funnel_actions,
        plan.blended_spend if plan.blended_spend else None,
    )

    # 5. Persist Run + Decision rows
    run = Run(
        tenant_id=tenant_id,
        line_item_id=line_item.id,
        week_label=week_label,
        window_start=window_start,
        window_end=window_end,
        status="succeeded",
        started_at=now,
        completed_at=datetime.now(timezone.utc),
        blended_cpv_target=plan.cpv_target,
        blended_cpv_observed=plan.blended_cpv_observed if plan.blended_cpv_observed != float("inf") else None,
        blended_visits=plan.blended_visits,
        blended_spend=plan.blended_spend,
        blended_roas=blended_roas,
        n_decisions=len(plan.decisions),
        n_changes_proposed=len(plan.changed_decisions),
        n_changes_applied=0,
    )
    db.add(run)
    await db.flush()  # ensures run.id is populated

    for d in plan.decisions:
        decision = Decision(
            tenant_id=tenant_id,
            run_id=run.id,
            targeting_module=d.term.targeting_module,
            targeting_key=d.term.targeting_key,
            value=str(d.term.value),
            field_label=d.term.field_label,
            previous_modifier=d.previous_modifier,
            new_modifier=d.new_modifier,
            reason=d.reason.value,
            note=d.note,
            observed_impressions=d.observed_impressions,
            observed_visits=d.observed_visits,
            observed_cpv=d.observed_cpv if d.observed_cpv != float("inf") else None,
            status="proposed",
        )
        db.add(decision)

    # 6. Generate the digest
    digest_cfg = DigestConfig.from_env()
    digest_cfg.language = digest_language  # type: ignore[assignment]
    try:
        digest_text = generate_digest(plan, config=digest_cfg)
        run.digest_text = digest_text
        run.digest_generated_at = datetime.now(timezone.utc)
    except Exception as e:  # noqa: BLE001
        log.warning("Digest generation failed for run %s: %s", run.id, e)

    await db.flush()

    # 7. Auto-apply when configured and past observation window
    if line_item.mode == "auto_apply":
        blocked, _reason = is_observation_only(line_item, setting)
        if not blocked:
            for decision in (
                await db.execute(
                    select(Decision).where(Decision.run_id == run.id)
                )
            ).scalars():
                if decision.new_modifier != decision.previous_modifier:
                    decision.status = "approved"
            await db.flush()
            try:
                run = await apply_run_to_dsp(
                    db,
                    tenant_id=tenant_id,
                    run_id=run.id,
                )
            except DspApplyError as e:
                log.warning("Auto-apply skipped for run %s: %s", run.id, e)

    return run


async def run_for_all_active_line_items(db: AsyncSession) -> list[Run]:
    """The weekly cron job. Iterates every tenant's active line items
    and runs the agent on each one."""
    result = await db.execute(
        select(LineItem)
        .join(Tenant, Tenant.id == LineItem.tenant_id)
        .where(LineItem.status == "active")
        .where(Tenant.status == "active")
    )
    line_items = result.scalars().all()
    log.info("Running weekly schedule on %d active line items", len(line_items))

    runs: list[Run] = []
    for li in line_items:
        try:
            run = await run_for_line_item(
                db, tenant_id=li.tenant_id, line_item_id=li.id,
            )
            runs.append(run)
        except Exception as e:  # noqa: BLE001
            log.exception("Run failed for line item %s: %s", li.id, e)
    return runs
