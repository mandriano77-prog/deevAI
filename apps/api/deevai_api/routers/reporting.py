"""Reporting endpoints — read-only KPIs and decision insight per run.

All routes here are protected by ``get_current_user_claims`` (Bearer
JWT required) — this is the customer-facing dashboard surface, so we
don't accept the dev ``X-Tenant-Id`` header fallback. The tenant scope
is taken from the JWT ``tid`` claim.

Everything is read-only: no DSP calls, no mutations, safe under any
DSP_DRY_RUN setting."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user_claims
from ..schemas.reporting import (
    ConstraintEventDTO,
    MoverDTO,
    RunSummaryDTO,
)
from ..services.reporting import (
    get_constraint_events,
    get_line_item_run_summaries,
    get_run_summary,
    get_top_movers,
    line_item_exists_for_tenant,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reporting"])


def _tenant_from_claims(claims: dict) -> str:
    tid = claims.get("tid")
    if not tid or not isinstance(tid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing tenant_id claim",
        )
    return tid


@router.get("/runs/{run_id}", response_model=RunSummaryDTO)
async def report_run_summary(
    run_id: str,
    claims: dict = Depends(get_current_user_claims),
    db: AsyncSession = Depends(get_session),
) -> RunSummaryDTO:
    """Top-line KPIs + decision distribution for a single Run."""
    tenant_id = _tenant_from_claims(claims)
    summary = await get_run_summary(db, run_id=run_id, tenant_id=tenant_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found",
        )
    return summary


@router.get("/runs/{run_id}/movers", response_model=list[MoverDTO])
async def report_run_movers(
    run_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    claims: dict = Depends(get_current_user_claims),
    db: AsyncSession = Depends(get_session),
) -> list[MoverDTO]:
    """Top N modifier movers (largest |delta|) for this run."""
    tenant_id = _tenant_from_claims(claims)
    # Distinguish 'no such run' from 'run exists but no movers' so the
    # FE renders the right empty state. Cheap second check; safer.
    summary = await get_run_summary(db, run_id=run_id, tenant_id=tenant_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found",
        )
    return await get_top_movers(
        db, run_id=run_id, tenant_id=tenant_id, limit=limit,
    )


@router.get("/runs/{run_id}/constraints", response_model=list[ConstraintEventDTO])
async def report_run_constraints(
    run_id: str,
    claims: dict = Depends(get_current_user_claims),
    db: AsyncSession = Depends(get_session),
) -> list[ConstraintEventDTO]:
    """Hard-constraint hits recorded during this run."""
    tenant_id = _tenant_from_claims(claims)
    summary = await get_run_summary(db, run_id=run_id, tenant_id=tenant_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found",
        )
    return await get_constraint_events(
        db, run_id=run_id, tenant_id=tenant_id,
    )


@router.get(
    "/line-items/{line_item_id}/runs",
    response_model=list[RunSummaryDTO],
)
async def report_line_item_runs(
    line_item_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    claims: dict = Depends(get_current_user_claims),
    db: AsyncSession = Depends(get_session),
) -> list[RunSummaryDTO]:
    """Last N run summaries for a line item, newest first."""
    tenant_id = _tenant_from_claims(claims)
    if not await line_item_exists_for_tenant(
        db, line_item_id=line_item_id, tenant_id=tenant_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="LineItem not found",
        )
    return await get_line_item_run_summaries(
        db, line_item_id=line_item_id, tenant_id=tenant_id, limit=limit,
    )
