"""LLM fallback for meta-agent diagnosis (Anthropic Claude)."""

from __future__ import annotations

import json
import logging
from typing import Any

from ...config import get_settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Sei il meta-agente di deevAI. Diagnostichi problemi su un bidding multi-objective.
Output rigorosamente JSON: {
  "diagnosis": str (max 5 frasi, italiano, tecnico),
  "proposed_changes": [{"entity": str, "entity_id": str, "field": str, "from": any, "to": any, "reason": str}],
  "expected_impact": {"primary_objective_delta_pct": float, "volume_delta_pct": float, "confidence": "low|med|high"}
}
Regole:
- Massimo 2 changes
- Tocchi entity 'settings' senza approvazione, tutto il resto richiede approvazione
- Mai modificare actions.tracking_source, actions.dedupe_rule, actions.type, settings.observation_only_until
- Se diagnosi è "trade-off sano" o "drop downstream", proposed_changes = []"""


async def diagnose(context: dict[str, Any], brief: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {
            "diagnosis": "LLM non configurato (ANTHROPIC_API_KEY mancante). Nessuna proposta automatica.",
            "proposed_changes": [],
            "expected_impact": None,
        }

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_content = f"{json.dumps(context, default=str)}\n\nBrief: {brief}"

    message = await client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = message.content[0].text if message.content else "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Meta-agent LLM returned non-JSON: %s", raw[:200])
        return {
            "diagnosis": raw[:500],
            "proposed_changes": [],
            "expected_impact": None,
        }
