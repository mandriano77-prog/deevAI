"""M.AI router — natural-language orchestration."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_tenant_id, get_optional_user_id
from ..routing import CamelCaseRouter
from ..schemas.mai import MaiAskIn, MaiAskOut, MaiExecuteIn, MaiExecuteOut, MaiHistoryOut, MaiLogItem
from ..models import LineItem
from ..services.mai.context import build_mai_context
from ..services.mai.dispatcher import dispatch_mai_execute
from ..services.mai.enrich import enrich_ask_response
from ..services.mai.llm import build_user_message, call_mai
from ..services.mai.logger import list_mai_log, log_mai_interaction
from ..services.mai.prompts import MAI_SYSTEM_PROMPT
from ..services.mai.rate_limit import check_mai_ask_rate
from ..services.mai.validator import validate_mai_ask_response

router = CamelCaseRouter(prefix="/mai", tags=["mai"])


async def _assert_payload_line_item(
    db: AsyncSession,
    *,
    tenant_id: str,
    payload: dict,
) -> None:
    li_id = payload.get("line_item_id")
    if not li_id:
        return
    item = await db.get(LineItem, str(li_id))
    if item is None or item.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")


@router.post("/ask", response_model=MaiAskOut)
async def ask_mai(
    body: MaiAskIn,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> MaiAskOut:
    check_mai_ask_rate(tenant_id)
    context = await build_mai_context(db, tenant_id=tenant_id, line_item_id=body.line_item_id)
    user_message = build_user_message(body.prompt, context)
    try:
        llm = await call_mai(MAI_SYSTEM_PROMPT, user_message)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e

    try:
        validated = validate_mai_ask_response(llm["parsed"])
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"M.AI schema validation failed: {e}",
        ) from e

    validated = await enrich_ask_response(
        db,
        tenant_id=tenant_id,
        line_item_id=body.line_item_id,
        validated=validated,
    )

    await log_mai_interaction(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        line_item_id=body.line_item_id,
        prompt=body.prompt,
        intent=validated.intent,
        proposal=validated.model_dump(mode="json"),
        action="planned",
        input_tokens=llm["input_tokens"],
        output_tokens=llm["output_tokens"],
    )
    return validated


@router.post("/execute", response_model=MaiExecuteOut)
async def execute_mai(
    body: MaiExecuteIn,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_session),
) -> MaiExecuteOut:
    line_li = None
    if body.intent in ("setup.brief", "tuning.brief"):
        line_li = body.payload.get("line_item_id")
        if isinstance(line_li, str):
            pass
        elif line_li is not None:
            line_li = str(line_li)

    await _assert_payload_line_item(db, tenant_id=tenant_id, payload=body.payload)

    result = await dispatch_mai_execute(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        intent=body.intent,
        payload=body.payload,
    )

    await log_mai_interaction(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        line_item_id=line_li,
        prompt=None,
        intent=body.intent,
        proposal=None,
        action="executed",
        payload=body.payload,
    )

    return MaiExecuteOut(
        success=result["success"],
        message=result["message"],
        data=result.get("data"),
    )


@router.get("/history", response_model=MaiHistoryOut)
async def mai_history(
    line_item_id: str | None = Query(default=None, alias="lineItemId"),
    limit: int = Query(default=20, ge=1, le=100),
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
) -> MaiHistoryOut:
    rows = await list_mai_log(db, tenant_id=tenant_id, line_item_id=line_item_id, limit=limit)
    items: list[MaiLogItem] = []
    for r in rows:
        items.append(
            MaiLogItem(
                id=r.id,
                line_item_id=r.line_item_id,
                prompt=r.prompt,
                intent=r.intent,
                action=r.action,
                proposal=r.proposal,
                payload=r.payload,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                created_at=r.created_at.isoformat(),
            ),
        )
    return MaiHistoryOut(items=items)
