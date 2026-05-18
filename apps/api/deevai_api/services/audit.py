"""Audit log writer — call from mutating API handlers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def snapshot_row(obj: Any) -> dict[str, Any] | None:
    """Serialize an ORM instance to a JSON-safe dict for audit before/after."""
    if obj is None:
        return None
    table = getattr(obj, "__table__", None)
    if table is None:
        return None
    return _json_safe({col.name: getattr(obj, col.name) for col in table.columns})


async def write_audit(
    session: AsyncSession,
    *,
    tenant_id: str,
    user_id: str | None = None,
    actor_user_id: str | None = None,
    actor_type: str = "user",
    entity: str,
    entity_id: str,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    proposal_id: str | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id if actor_user_id is not None else user_id,
            actor_type=actor_type,
            entity=entity,
            entity_id=entity_id,
            action=action,
            before=before,
            after=after,
            proposal_id=proposal_id,
        ),
    )
