"""Studio endpoints — Custom Bidding script generation + simulation.

Routes
------
- ``POST   /v1/studio/scripts``                    create + persist (status=draft)
- ``GET    /v1/studio/scripts``                    list (filter by status, paginated)
- ``GET    /v1/studio/scripts/{id}``               full detail incl. script_source
- ``POST   /v1/studio/scripts/{id}/simulate``      run synthetic-dataset simulation
- ``DELETE /v1/studio/scripts/{id}``               soft-archive (no physical delete)

Auth
----
Bearer JWT required on every route (same pattern as ``reporting.py``).
Cross-tenant access returns ``404`` — we never confirm that another
tenant's script exists.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user_claims
from ..schemas.studio import (
    ScriptCreateRequest,
    ScriptDetailDTO,
    ScriptDTO,
    SimulationReportDTO,
    SimulationRequest,
)
from ..services.studio import (
    archive_script,
    create_script,
    get_script,
    list_scripts,
    simulate_script,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/studio", tags=["studio"])


def _tenant_from_claims(claims: dict) -> str:
    tid = claims.get("tid")
    if not tid or not isinstance(tid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing tenant_id claim",
        )
    return tid


def _user_from_claims(claims: dict) -> str | None:
    sub = claims.get("sub")
    return sub if isinstance(sub, str) else None


# --------------------------------------------------------- POST /scripts


@router.post(
    "/scripts",
    response_model=ScriptDTO,
    status_code=status.HTTP_201_CREATED,
)
async def studio_create_script(
    payload: ScriptCreateRequest,
    claims: dict = Depends(get_current_user_claims),
    db: AsyncSession = Depends(get_session),
) -> ScriptDTO:
    """Generate the DSL from the supplied weights and persist it."""
    tenant_id = _tenant_from_claims(claims)
    user_id = _user_from_claims(claims)
    return await create_script(
        db, tenant_id=tenant_id, user_id=user_id, payload=payload,
    )


# ---------------------------------------------------------- GET /scripts


@router.get("/scripts", response_model=list[ScriptDTO])
async def studio_list_scripts(
    status_: str | None = Query(
        default=None, alias="status",
        description="Optional status filter (e.g. draft, simulated, archived).",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    claims: dict = Depends(get_current_user_claims),
    db: AsyncSession = Depends(get_session),
) -> list[ScriptDTO]:
    """List scripts for the current tenant (archived excluded by default)."""
    tenant_id = _tenant_from_claims(claims)
    return await list_scripts(
        db,
        tenant_id=tenant_id,
        status=status_,
        limit=limit,
        offset=offset,
    )


# ----------------------------------------------------- GET /scripts/{id}


@router.get("/scripts/{script_id}", response_model=ScriptDetailDTO)
async def studio_get_script(
    script_id: str,
    claims: dict = Depends(get_current_user_claims),
    db: AsyncSession = Depends(get_session),
) -> ScriptDetailDTO:
    """Return the full script detail + the latest simulation, if any."""
    tenant_id = _tenant_from_claims(claims)
    detail = await get_script(db, tenant_id=tenant_id, script_id=script_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Script not found",
        )
    return detail


# ------------------------------------------- POST /scripts/{id}/simulate


@router.post(
    "/scripts/{script_id}/simulate",
    response_model=SimulationReportDTO,
)
async def studio_simulate_script(
    script_id: str,
    payload: SimulationRequest | None = None,
    claims: dict = Depends(get_current_user_claims),
    db: AsyncSession = Depends(get_session),
) -> SimulationReportDTO:
    """Run the score simulator against the script and persist the result."""
    tenant_id = _tenant_from_claims(claims)
    body = payload or SimulationRequest()
    report = await simulate_script(
        db, tenant_id=tenant_id, script_id=script_id, payload=body,
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Script not found",
        )
    return report


# -------------------------------------------------- DELETE /scripts/{id}


@router.delete(
    "/scripts/{script_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def studio_archive_script(
    script_id: str,
    claims: dict = Depends(get_current_user_claims),
    db: AsyncSession = Depends(get_session),
) -> None:
    """Soft-delete: flip the status to ``archived``. Idempotent for archived rows."""
    tenant_id = _tenant_from_claims(claims)
    ok = await archive_script(db, tenant_id=tenant_id, script_id=script_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Script not found",
        )
