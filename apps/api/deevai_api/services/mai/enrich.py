"""Post-process M.AI ask responses with deterministic DB readers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas.mai import MaiAskOut
from .readers import QUERY_INTENTS, help_answer, run_query_reader


async def enrich_ask_response(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    validated: MaiAskOut,
) -> MaiAskOut:
    if validated.intent == "help":
        answer, details = help_answer()
        return validated.model_copy(
            update={
                "type": "system",
                "answer": answer,
                "preview": validated.preview.model_copy(
                    update={
                        "summary": answer,
                        "details": {**validated.preview.details, **details},
                    },
                ),
            },
        )

    if validated.type != "query" or validated.intent not in QUERY_INTENTS:
        return validated

    answer, details = await run_query_reader(
        db,
        tenant_id=tenant_id,
        line_item_id=line_item_id,
        intent=validated.intent,
        payload=validated.payload,
    )
    return validated.model_copy(
        update={
            "answer": answer,
            "preview": validated.preview.model_copy(
                update={
                    "summary": validated.preview.summary or answer[:200],
                    "details": {**validated.preview.details, **details},
                },
            ),
        },
    )
