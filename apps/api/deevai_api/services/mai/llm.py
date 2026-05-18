"""Anthropic client for M.AI."""

from __future__ import annotations

import json
import os
import re

from anthropic import AsyncAnthropic


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


async def call_mai(system_prompt: str, user_message: str) -> dict:
    """Call Claude and parse JSON body. Raises ValueError on bad JSON or missing key."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = AsyncAnthropic(api_key=api_key, timeout=60.0, max_retries=2)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    text = response.content[0].text
    raw = _strip_json_fence(text)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"M.AI ha risposto con JSON invalido: {e}") from e

    return {
        "parsed": parsed,
        "input_tokens": getattr(response.usage, "input_tokens", None),
        "output_tokens": getattr(response.usage, "output_tokens", None),
    }


def build_user_message(prompt: str, context: dict) -> str:
    return (
        f"Stato attuale:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
        f"Richiesta dell'advertiser:\n{prompt}"
    )
