"""Apply approved Setup Agent proposals (batch create + funnel resolution)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Action, AgentProposal, HardConstraint, OptimizationStrategy, Setting, utcnow
from ...services.actions import set_action_funnel
from ...services.audit import snapshot_row, write_audit

_STRATEGY_KEYS = {
    "mode", "primary_metric", "primary_target", "primary_weight",
    "secondary_metric", "secondary_target", "secondary_weight",
    "tertiary_metric", "tertiary_target", "tertiary_weight",
    "primary_action_id", "tolerance_band", "status", "line_item_id",
}
_ACTION_KEYS = {
    "name", "type", "weight", "value_eur", "value_source", "value_currency",
    "tracking_source", "attribution_window_hours", "dedupe_rule", "quality_filter",
    "funnel_position", "status", "line_item_id",
}
_CONSTRAINT_KEYS = {"metric", "operator", "value", "violation_policy", "status"}


def _pick(payload: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k in allowed and v is not None}


async def apply_proposal(
    db: AsyncSession,
    *,
    proposal_id: str,
    user_id: str | None,
) -> AgentProposal:
    proposal = await db.get(AgentProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "approved":
        raise HTTPException(status_code=422, detail="Proposal must be approved before apply")

    strategy_id: str | None = None
    action_rows: list[Action] = []
    action_meta: list[dict[str, Any]] = []
    funnel_order: list[str] = []
    deferred_constraints: list[dict[str, Any]] = []
    other_changes: list[dict[str, Any]] = []

    for change in proposal.proposed_changes:
        entity = change.get("entity", "")
        if entity in ("optimization_strategy", "optimization_strategies"):
            if change.get("operation") == "create":
                payload = _pick(change.get("payload") or {}, _STRATEGY_KEYS)
                row = OptimizationStrategy(tenant_id=proposal.tenant_id, **payload)
                db.add(row)
                await db.flush()
                strategy_id = row.id
                await write_audit(
                    db,
                    tenant_id=proposal.tenant_id,
                    actor_user_id=user_id,
                    actor_type="setup_agent",
                    entity="optimization_strategies",
                    entity_id=row.id,
                    action="create",
                    before=None,
                    after=snapshot_row(row),
                    proposal_id=proposal.id,
                )
        elif entity in ("action", "actions") and change.get("operation") == "create":
            payload = dict(change.get("payload") or {})
            funnel_order.append(payload.get("name") or change.get("entity_id") or "")
            meta = {
                "funnel_parent_name": payload.pop("funnel_parent_name", None),
                "funnel_parent_id": payload.pop("funnel_parent_id", None),
            }
            clean = _pick(payload, _ACTION_KEYS)
            row = Action(tenant_id=proposal.tenant_id, **clean)
            db.add(row)
            action_rows.append(row)
            action_meta.append(meta)
        elif entity in ("hard_constraint", "hard_constraints"):
            deferred_constraints.append(change)
        else:
            other_changes.append(change)

    await db.flush()

    name_to_id = {a.name: a.id for a in action_rows}
    for row, meta in zip(action_rows, action_meta, strict=True):
        parent_id = meta.get("funnel_parent_id")
        parent_name = meta.get("funnel_parent_name")
        if parent_id:
            row.funnel_parent_id = parent_id
        elif parent_name and parent_name in name_to_id:
            row.funnel_parent_id = name_to_id[parent_name]
        await write_audit(
            db,
            tenant_id=proposal.tenant_id,
            actor_user_id=user_id,
            actor_type="setup_agent",
            entity="actions",
            entity_id=row.id,
            action="create",
            before=None,
            after=snapshot_row(row),
            proposal_id=proposal.id,
        )

    if funnel_order:
        ordered_ids = [name_to_id[n] for n in funnel_order if n in name_to_id]
        if len(ordered_ids) >= 2:
            await set_action_funnel(
                db,
                tenant_id=proposal.tenant_id,
                ordered_action_ids=ordered_ids,
            )
    elif len(action_rows) >= 2:
        await set_action_funnel(
            db,
            tenant_id=proposal.tenant_id,
            ordered_action_ids=[a.id for a in action_rows],
        )

    sid = strategy_id
    for change in deferred_constraints:
        if change.get("operation") != "create":
            continue
        payload = dict(change.get("payload") or {})
        if not sid:
            sid = payload.pop("optimization_strategy_id", None)
        if not sid:
            raise HTTPException(422, detail="optimization_strategy required before constraints")
        clean = _pick(payload, _CONSTRAINT_KEYS)
        row = HardConstraint(
            tenant_id=proposal.tenant_id,
            optimization_strategy_id=sid,
            **clean,
        )
        db.add(row)
        await db.flush()
        await write_audit(
            db,
            tenant_id=proposal.tenant_id,
            actor_user_id=user_id,
            actor_type="setup_agent",
            entity="hard_constraints",
            entity_id=row.id,
            action="create",
            before=None,
            after=snapshot_row(row),
            proposal_id=proposal.id,
        )

    for change in other_changes:
        if change.get("entity") == "settings" and change.get("operation") == "update":
            entity_id = change.get("entity_id")
            payload = change.get("payload") or {change["field"]: change.get("to")}
            if not entity_id:
                continue
            row = await db.get(Setting, entity_id)
            if row is None or row.tenant_id != proposal.tenant_id:
                raise HTTPException(404, detail="Setting not found")
            before = snapshot_row(row)
            for k, v in payload.items():
                if hasattr(row, k):
                    setattr(row, k, v)
            await write_audit(
                db,
                tenant_id=proposal.tenant_id,
                actor_user_id=user_id,
                actor_type="setup_agent",
                entity="settings",
                entity_id=entity_id,
                action="update",
                before=before,
                after=snapshot_row(row),
                proposal_id=proposal.id,
            )

    proposal.status = "applied"
    proposal.applied_at = utcnow()
    proposal.post_mortem_due_at = utcnow() + timedelta(days=7)
    await db.flush()
    return proposal
