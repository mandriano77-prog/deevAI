"""Run endpoints — trigger a run, list runs, fetch decisions."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id
from ..models import Decision, Run
from ..schemas.run import (
    DecisionRead,
    DecisionUpdateRequest,
    RunApplyRequest,
    RunRead,
    RunTriggerRequest,
)
from ..services.dsp_apply import DspApplyError, apply_run_to_dsp
from ..services.scheduler import run_for_line_item

log = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("/trigger", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    payload: Annotated[RunTriggerRequest, Body()],
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> Run:
    """Manually trigger a bidagent run on a specific line item.

    Useful for: testing, regenerating after settings changed, on-demand
    'pull the latest data and show me what you'd change'."""
    try:
        run = await run_for_line_item(
            db,
            tenant_id=tenant_id,
            line_item_id=payload.line_item_id,
            digest_language=payload.language,
        )
        return run
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        ) from e


@router.get("", response_model=list[RunRead])
async def list_runs(
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    line_item_id: str | None = None,
    limit: int = 20,
) -> list[Run]:
    """List runs for the current tenant, optionally filtered by line item."""
    query = (
        select(Run)
        .where(Run.tenant_id == tenant_id)
        .order_by(desc(Run.started_at))
        .limit(limit)
    )
    if line_item_id:
        query = query.where(Run.line_item_id == line_item_id)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{run_id}", response_model=RunRead)
async def get_run(
    run_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> Run:
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found",
        )
    return run


@router.get("/{run_id}/decisions", response_model=list[DecisionRead])
async def get_run_decisions(
    run_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> list[Decision]:
    """Decisions generated for a specific run."""
    # Make sure the run belongs to this tenant first
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found",
        )
    result = await db.execute(
        select(Decision).where(Decision.run_id == run_id).order_by(Decision.created_at)
    )
    return list(result.scalars().all())


@router.patch("/decisions/{decision_id}", response_model=DecisionRead)
async def update_decision_status(
    decision_id: str,
    payload: Annotated[DecisionUpdateRequest, Body()],
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> Decision:
    """Approve / reject a decision. (Apply happens via a separate path
    in Sprint 3, when the DSP API push is wired.)"""
    decision = await db.get(Decision, decision_id)
    if decision is None or decision.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found",
        )

    if payload.status not in ("approved", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be 'approved' or 'rejected'",
        )

    from ..models.base import utcnow
    decision.status = payload.status
    decision.reviewed_at = utcnow()
    return decision


@router.post("/{run_id}/apply", response_model=RunRead)
async def apply_run(
    run_id: str,
    payload: RunApplyRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> Run:
    """Apply all approved decisions from a run to Amazon DSP bid adjustment rules."""
    try:
        return await apply_run_to_dsp(
            db,
            tenant_id=tenant_id,
            run_id=run_id,
            force=payload.force,
        )
    except DspApplyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
