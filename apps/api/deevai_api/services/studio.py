"""Service layer for Studio — create/list/get/simulate/archive scripts.

This is the only place that talks directly to the
``bidagent.engines.custom_bidding`` package; the router stays thin.

Design notes
------------
- The service treats Engine B's foundation as read-only — we *consume*
  ``generate_script`` / ``validate_script`` / ``ScoreSimulator`` and
  never reach into their internals.
- The Studio's identity for a script is its sha256 over the generated
  source. Same weights + same name + same tenant → same source bytes →
  same sha256, which is exactly what the FE relies on for de-dupe and
  change-management.
- Tenant scoping is enforced at every query. Cross-tenant access
  returns ``None`` (the router maps that to 404 — same pattern as
  reporting).
- Status transitions are intentionally narrow in v1:
    * ``draft`` on create
    * ``draft → simulated`` after a successful simulation
    * ``* → archived`` via DELETE (soft delete, no physical removal)
  Upload/active transitions land in a later sprint.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Iterable, Optional

from fastapi import HTTPException, status as http_status
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CustomBiddingScript,
    LineItem,
    ObjectiveWeight,
    SimulationRun,
)
from ..schemas.studio import (
    DistributionStats,
    ImpressionScoreDTO,
    ObjectiveWeightsDTO,
    ScriptCreateRequest,
    ScriptDetailDTO,
    ScriptDTO,
    SimulationReportDTO,
    SimulationRequest,
)

# Engine B foundation — consumed verbatim, never modified.
from bidagent.engines.custom_bidding import (  # type: ignore[import-not-found]
    ObjectiveId,
    ScoreSimulator,
    SimulationDataset,
    TenantConfig,
    generate_synthetic_dataset,
    generate_script,
    validate_script,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────── helpers


def _weights_to_tenant_config(weights: ObjectiveWeightsDTO) -> TenantConfig:
    """Convert int-percent slider weights to the engine's float-in-[0..1] form.

    The engine tolerates ±0.001 on the sum; integer percent / 100 is
    bit-stable for the (P, Q, R) triplets we care about.
    """
    cfg_weights = {
        ObjectiveId.PERFORMANCE: weights.performance / 100.0,
        ObjectiveId.QUALITY: weights.quality / 100.0,
        ObjectiveId.REACH: weights.reach / 100.0,
    }
    # If performance > 0 the engine needs a floodlight activity id; we
    # default to a stable placeholder so the customer can simulate
    # before they've wired Floodlight. The script generator embeds the
    # ID in the comment header, so customers see exactly what they'll
    # need to swap out before going live.
    fl_id: int | None = None
    if weights.performance > 0:
        fl_id = 999_999
    return TenantConfig(
        weights=cfg_weights,
        floodlight_activity_id=fl_id,
    )


def _ow_to_dto(ow: ObjectiveWeight | None) -> ObjectiveWeightsDTO:
    if ow is None:
        # Shouldn't happen in practice (we always write the row), but
        # safer than crashing the dashboard if a row is missing.
        return ObjectiveWeightsDTO(performance=100, quality=0, reach=0)
    return ObjectiveWeightsDTO(
        performance=ow.performance_pct,
        quality=ow.quality_pct,
        reach=ow.reach_pct,
    )


def _script_to_dto(
    script: CustomBiddingScript,
    weights: ObjectiveWeight | None,
) -> ScriptDTO:
    return ScriptDTO(
        id=script.id,
        tenant_id=script.tenant_id,
        line_item_id=script.line_item_id,
        name=script.name,
        status=script.status,
        script_sha256=script.script_sha256,
        size_bytes=script.size_bytes,
        weights=_ow_to_dto(weights),
        created_at=script.created_at,
        updated_at=script.updated_at,
    )


def _sim_to_dto(
    run: SimulationRun,
    *,
    top_winners: Iterable[ImpressionScoreDTO] = (),
    top_losers: Iterable[ImpressionScoreDTO] = (),
) -> SimulationReportDTO:
    dist_raw = run.distribution_json or {}
    distribution = DistributionStats(
        p10=float(dist_raw.get("p10", 0.0)),
        p25=float(dist_raw.get("p25", 0.0)),
        p50=float(dist_raw.get("p50", 0.0)),
        p75=float(dist_raw.get("p75", 0.0)),
        p90=float(dist_raw.get("p90", 0.0)),
        p99=float(dist_raw.get("p99", 0.0)),
        mean=float(dist_raw.get("mean", 0.0)),
        stddev=float(dist_raw.get("stddev", 0.0)),
        pct_above_500=float(dist_raw.get("pct_above_500", 0.0)),
    )
    return SimulationReportDTO(
        id=run.id,
        script_id=run.script_id,
        dataset_kind=run.dataset_kind,
        n_impressions=run.n_impressions,
        n_scored=run.n_scored,
        n_excluded=run.n_excluded,
        pct_above_500=distribution.pct_above_500,
        distribution=distribution,
        top_winners=list(top_winners),
        top_losers=list(top_losers),
        duration_ms=run.duration_ms,
        created_at=run.created_at,
    )


# ─────────────────────────────────────────────── create


async def create_script(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: Optional[str],
    payload: ScriptCreateRequest,
) -> ScriptDTO:
    """Generate the DSL, validate it, persist script + weights.

    Raises HTTPException 422 on engine validation failures, 409 on
    duplicate (tenant_id, name), and 422 if a line_item_id is
    supplied that doesn't belong to the calling tenant.
    """
    # Guard against cross-tenant line_item_id smuggling.
    if payload.line_item_id is not None:
        result = await db.execute(
            select(LineItem.id).where(
                LineItem.id == payload.line_item_id,
                LineItem.tenant_id == tenant_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="line_item_id does not belong to this tenant",
            )

    cfg = _weights_to_tenant_config(payload.weights)
    try:
        generated = generate_script(cfg, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Engine refused to generate script: {exc}",
        ) from exc

    report = validate_script(generated.source)
    if not report.ok:
        # Surface the first error — the validator emits actionable
        # messages, no need to dump them all.
        first = report.errors()[0] if report.errors() else None
        msg = first.message if first else "validator rejected generated script"
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Generated script failed sandbox validation: {msg}",
        )

    script = CustomBiddingScript(
        tenant_id=tenant_id,
        line_item_id=payload.line_item_id,
        name=payload.name,
        status="draft",
        script_source=generated.source,
        script_sha256=generated.digest_sha256,
        size_bytes=len(generated.source.encode("utf-8")),
        created_by_user_id=user_id,
    )
    db.add(script)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="A script with this name already exists for the tenant.",
        ) from exc

    weights_row = ObjectiveWeight(
        script_id=script.id,
        performance_pct=payload.weights.performance,
        quality_pct=payload.weights.quality,
        reach_pct=payload.weights.reach,
    )
    db.add(weights_row)
    await db.flush()

    return _script_to_dto(script, weights_row)


# ─────────────────────────────────────────────── simulate


async def simulate_script(
    db: AsyncSession,
    *,
    tenant_id: str,
    script_id: str,
    payload: SimulationRequest,
) -> SimulationReportDTO | None:
    """Run the simulator and persist a SimulationRun.

    Returns None when the script doesn't exist (or belongs to another
    tenant — same outcome from the caller's perspective). On success
    we also flip ``status`` from ``draft`` to ``simulated`` (idempotent;
    once-simulated stays simulated).
    """
    script = await _load_script(db, tenant_id=tenant_id, script_id=script_id)
    if script is None:
        return None

    started = time.perf_counter()

    if payload.dataset_kind == "synthetic":
        dataset: SimulationDataset = generate_synthetic_dataset(
            n=payload.n_impressions,
            seed=42,  # deterministic — re-simulate same script = same report
        )
    else:
        # Floodlight-historical dataset support arrives with the
        # measurement integration. Until then we 501 rather than
        # silently fall back to synthetic.
        raise HTTPException(
            status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "floodlight_historical dataset is not yet wired — "
                "ship Floodlight ingestion before requesting it here."
            ),
        )

    try:
        simulator = ScoreSimulator(script.script_source)
        report = simulator.simulate(dataset)
    except Exception as exc:  # pragma: no cover — defensive
        log.exception("score simulator crashed for script_id=%s", script_id)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Simulation failed: {exc}",
        ) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)

    distribution_json = {
        **report.value_distribution,
        "pct_above_500": report.pct_above_500,
    }

    run = SimulationRun(
        tenant_id=tenant_id,
        script_id=script.id,
        dataset_kind=payload.dataset_kind,
        n_impressions=report.n_impressions,
        n_scored=report.n_scored,
        n_excluded=report.n_excluded,
        distribution_json=distribution_json,
        duration_ms=duration_ms,
    )
    db.add(run)

    # Lifecycle bump: draft → simulated. Anything beyond stays put.
    if script.status == "draft":
        script.status = "simulated"
    await db.flush()

    return _sim_to_dto(
        run,
        top_winners=[
            ImpressionScoreDTO(
                impression_id=w.impression_id,
                score=float(w.score) if w.score is not None else 0.0,
                used_signals=list(w.used_signals),
            )
            for w in report.top_winners[:5]
        ],
        top_losers=[
            ImpressionScoreDTO(
                impression_id=l.impression_id,
                score=float(l.score) if l.score is not None else 0.0,
                used_signals=list(l.used_signals),
            )
            for l in report.top_losers[:5]
        ],
    )


# ─────────────────────────────────────────────── list / get


async def list_scripts(
    db: AsyncSession,
    *,
    tenant_id: str,
    status: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[ScriptDTO]:
    """List scripts for a tenant, newest first.

    By default ``archived`` rows are excluded — they're a soft-delete
    bucket, not a normal listing. Pass ``include_archived=True`` (or a
    ``status="archived"`` filter) to see them.
    """
    stmt = select(CustomBiddingScript).where(
        CustomBiddingScript.tenant_id == tenant_id,
    )
    if status is not None:
        stmt = stmt.where(CustomBiddingScript.status == status)
    elif not include_archived:
        stmt = stmt.where(CustomBiddingScript.status != "archived")

    stmt = stmt.order_by(desc(CustomBiddingScript.created_at)).limit(limit).offset(offset)

    result = await db.execute(stmt)
    scripts: Sequence[CustomBiddingScript] = result.scalars().all()

    if not scripts:
        return []

    # Batch-fetch the weights rows so we don't N+1.
    ids = [s.id for s in scripts]
    weights_result = await db.execute(
        select(ObjectiveWeight).where(ObjectiveWeight.script_id.in_(ids))
    )
    weights_by_script: dict[str, ObjectiveWeight] = {
        ow.script_id: ow for ow in weights_result.scalars().all()
    }

    return [_script_to_dto(s, weights_by_script.get(s.id)) for s in scripts]


async def get_script(
    db: AsyncSession,
    *,
    tenant_id: str,
    script_id: str,
) -> ScriptDetailDTO | None:
    """Return the full script detail or ``None`` if not visible to the tenant."""
    script = await _load_script(db, tenant_id=tenant_id, script_id=script_id)
    if script is None:
        return None

    ow = await _load_weights(db, script_id=script.id)
    latest = await _load_latest_simulation(db, script_id=script.id)

    base = _script_to_dto(script, ow)
    return ScriptDetailDTO(
        **base.model_dump(by_alias=False),
        script_source=script.script_source,
        latest_simulation=latest,
    )


# ─────────────────────────────────────────────── archive (soft delete)


async def archive_script(
    db: AsyncSession,
    *,
    tenant_id: str,
    script_id: str,
) -> bool:
    """Soft-delete: flip status to ``archived``.

    Returns False when the script is unknown (or belongs to another
    tenant). We deliberately do **not** physically delete — the script
    may already have been uploaded to DV360, and we want the audit
    trail. The list endpoint hides archived rows by default.
    """
    script = await _load_script(db, tenant_id=tenant_id, script_id=script_id)
    if script is None:
        return False
    script.status = "archived"
    await db.flush()
    return True


# ─────────────────────────────────────────────── internal loaders


async def _load_script(
    db: AsyncSession, *, tenant_id: str, script_id: str,
) -> CustomBiddingScript | None:
    result = await db.execute(
        select(CustomBiddingScript).where(
            CustomBiddingScript.id == script_id,
            CustomBiddingScript.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def _load_weights(
    db: AsyncSession, *, script_id: str,
) -> ObjectiveWeight | None:
    result = await db.execute(
        select(ObjectiveWeight).where(ObjectiveWeight.script_id == script_id)
    )
    return result.scalar_one_or_none()


async def _load_latest_simulation(
    db: AsyncSession, *, script_id: str,
) -> SimulationReportDTO | None:
    result = await db.execute(
        select(SimulationRun)
        .where(SimulationRun.script_id == script_id)
        .order_by(desc(SimulationRun.created_at))
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        return None
    # We don't persist top winners/losers in the run row (too much data,
    # not needed for the dashboard refresh path), so we re-emit them as
    # empty lists. The /simulate response shipped them inline.
    return _sim_to_dto(run)


__all__ = [
    "create_script",
    "simulate_script",
    "list_scripts",
    "get_script",
    "archive_script",
]
