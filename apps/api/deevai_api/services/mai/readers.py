"""Deterministic query executors for M.AI — Italian narratives from DB facts."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import AgentProposal, Decision, LineItem, Run, utcnow
from ...services.audit import snapshot_row
from ...services.mai.context import build_mai_context
from ...services.optimization import resolve_effective_strategy

QUERY_INTENTS = frozenset({
    "dashboard.read",
    "run.last",
    "run.history",
    "decision.list",
    "decision.explain",
    "proposal.list",
    "proposal.detail",
    "strategy.read",
})


def _f(val: Decimal | float | int | None) -> float | None:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


def _pct_delta(observed: float | None, target: float | None) -> str:
    if observed is None or target is None or target <= 0:
        return "n/d"
    delta = (observed - target) / target * 100.0
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.0f}%"


async def get_dashboard(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    **_kwargs: Any,
) -> tuple[str, dict[str, Any]]:
    ctx = await build_mai_context(db, tenant_id=tenant_id, line_item_id=line_item_id)
    li = ctx["line_item"]
    ms = ctx.get("metrics_summary") or {}
    pending = ctx.get("proposals_pending") or []
    strategy = ctx.get("strategy")
    constraints = ctx.get("constraints") or []
    runs = ctx.get("runs_recent") or []

    primary_line = "legacy CPV"
    if strategy:
        pm = strategy.get("primary_metric", "cpv")
        pt = strategy.get("primary_target")
        primary_line = f"{pm} target {pt}"

    last_run = runs[0] if runs else None
    last_label = last_run.get("week_label") if last_run else "nessuna run"

    answer = (
        f"Line item «{li['name']}» in modalità {li['mode']}. "
        f"Ottimizzazione: {primary_line}. "
        f"{len(constraints)} constraint attivi, {len(pending)} proposte in attesa. "
        f"Ultima run: {last_label}."
    )
    if ms.get("last_blended_cpv_observed") is not None:
        answer += (
            f" CPV osservato {ms['last_blended_cpv_observed']:.2f}€"
            f" (movimento medio {ms.get('movement_rate_avg_last_3_runs', 0) * 100:.0f}% term/run)."
        )
    return answer, {"line_item": li, "metrics_summary": ms, "pending_count": len(pending)}


async def get_last_run(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    **_kwargs: Any,
) -> tuple[str, dict[str, Any]]:
    run = (
        await db.execute(
            select(Run)
            .where(Run.tenant_id == tenant_id, Run.line_item_id == line_item_id)
            .order_by(Run.window_end.desc())
            .limit(1),
        )
    ).scalar_one_or_none()
    if run is None:
        return "Non ci sono run registrate per questo line item.", {}

    snap = snapshot_row(run) or {}
    cpv = _f(run.blended_cpv_observed)
    target = _f(run.blended_cpv_target)
    answer = (
        f"Settimana {run.week_label}: stato {run.status}. "
        f"{run.n_decisions} decisioni, {run.n_changes_proposed} proposte, "
        f"{run.n_changes_applied} applicate."
    )
    if cpv is not None:
        answer += f" CPV {cpv:.2f}€ vs target {target:.2f}€ ({_pct_delta(cpv, target)})."
    if run.blended_visits is not None:
        answer += f" Visite {run.blended_visits:,}, spend {float(run.blended_spend or 0):.2f}€."
    return answer, {"run": snap}


async def get_run_history(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    limit: int = 4,
    **_kwargs: Any,
) -> tuple[str, dict[str, Any]]:
    lim = min(int(_kwargs.get("limit") or limit), 12)
    runs = (
        await db.execute(
            select(Run)
            .where(Run.tenant_id == tenant_id, Run.line_item_id == line_item_id)
            .order_by(Run.window_end.desc())
            .limit(lim),
        )
    ).scalars().all()
    if not runs:
        return "Nessuna run nello storico.", {"runs": []}

    parts: list[str] = []
    rows: list[dict[str, Any]] = []
    for r in runs:
        cpv = _f(r.blended_cpv_observed)
        rows.append(snapshot_row(r) or {})
        parts.append(
            f"{r.week_label}: CPV {cpv:.2f}€" if cpv is not None else f"{r.week_label}: senza CPV",
        )
    answer = f"Ultime {len(runs)} settimane: " + "; ".join(parts) + "."
    return answer, {"runs": rows}


async def get_term_decisions(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    run_id: str | None = None,
    reason: str | None = None,
    **_kwargs: Any,
) -> tuple[str, dict[str, Any]]:
    if run_id:
        target_run_id = run_id
    else:
        last = (
            await db.execute(
                select(Run)
                .where(Run.tenant_id == tenant_id, Run.line_item_id == line_item_id)
                .order_by(Run.window_end.desc())
                .limit(1),
            )
        ).scalar_one_or_none()
        if last is None:
            return "Nessuna run per elencare le decisioni.", {}
        target_run_id = last.id

    run = await db.get(Run, target_run_id)
    if run is None or run.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Run not found")

    stmt = select(Decision).where(Decision.run_id == target_run_id, Decision.tenant_id == tenant_id)
    if reason:
        stmt = stmt.where(Decision.reason == reason)
    decisions = (await db.execute(stmt.order_by(Decision.created_at.desc()).limit(40))).scalars().all()

    if not decisions:
        return f"Nessuna decisione per la run {run.week_label}.", {"run_id": target_run_id, "decisions": []}

    changed = [d for d in decisions if d.new_modifier != d.previous_modifier]
    answer = (
        f"Run {run.week_label}: {len(decisions)} decisioni"
        f" ({len(changed)} con modifier cambiato)."
    )
    if changed:
        sample = changed[0]
        label = sample.field_label or sample.value
        answer += (
            f" Esempio: {label} {float(sample.previous_modifier):.2f}"
            f" → {float(sample.new_modifier):.2f} [{sample.reason}]."
        )
    return answer, {
        "run_id": target_run_id,
        "decisions": [snapshot_row(d) for d in decisions[:20]],
    }


async def explain_decision(
    db: AsyncSession,
    *,
    tenant_id: str,
    decision_id: str,
    **_kwargs: Any,
) -> tuple[str, dict[str, Any]]:
    if not decision_id:
        return "Serve decision_id nel payload.", {}
    dec = await db.get(Decision, decision_id)
    if dec is None or dec.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Decision not found")

    label = dec.field_label or dec.value
    note = dec.note or ""
    answer = (
        f"{label} ({dec.targeting_module}/{dec.targeting_key}): "
        f"modifier {float(dec.previous_modifier):.2f} → {float(dec.new_modifier):.2f}. "
        f"Motivo: {dec.reason}."
    )
    if dec.observed_cpv is not None:
        answer += f" CPV osservato {float(dec.observed_cpv):.2f}€."
    if note:
        answer += f" {note}"
    return answer, {"decision": snapshot_row(dec)}


async def list_proposals_query(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    status_filter: str | None = None,
    **_kwargs: Any,
) -> tuple[str, dict[str, Any]]:
    stmt = select(AgentProposal).where(
        AgentProposal.tenant_id == tenant_id,
        AgentProposal.line_item_id == line_item_id,
    )
    if status_filter:
        stmt = stmt.where(AgentProposal.status == status_filter)
    rows = (
        await db.execute(stmt.order_by(AgentProposal.created_at.desc()).limit(20))
    ).scalars().all()

    if not rows:
        filt = f" con stato {status_filter}" if status_filter else ""
        return f"Nessuna proposta{filt}.", {"proposals": []}

    answer = f"{len(rows)} proposte" + (f" ({status_filter})" if status_filter else "") + ": "
    answer += "; ".join(
        f"{p.agent_type} {p.status} ({p.id[:8]}…)" for p in rows[:5]
    )
    if len(rows) > 5:
        answer += f" e altre {len(rows) - 5}."
    return answer, {"proposals": [snapshot_row(p) for p in rows]}


async def get_proposal_detail(
    db: AsyncSession,
    *,
    tenant_id: str,
    proposal_id: str,
    **_kwargs: Any,
) -> tuple[str, dict[str, Any]]:
    if not proposal_id:
        return "Serve proposal_id nel payload.", {}
    prop = await db.get(AgentProposal, proposal_id)
    if prop is None or prop.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Proposal not found")

    n_changes = len(prop.proposed_changes or [])
    answer = (
        f"Proposta {prop.agent_type} ({prop.status}): "
        f"{prop.diagnosis or prop.brief[:120]}. "
        f"{n_changes} modifiche proposte."
    )
    return answer, {"proposal": snapshot_row(prop)}


async def get_strategy(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    **_kwargs: Any,
) -> tuple[str, dict[str, Any]]:
    strategy = await resolve_effective_strategy(
        db, tenant_id=tenant_id, line_item_id=line_item_id,
    )
    if strategy is None:
        item = await db.get(LineItem, line_item_id)
        cpv = _f(item.cpv_target) if item else None
        return (
            f"Nessuna OptimizationStrategy: percorso legacy CPV"
            f"{f' target {cpv:.2f}€' if cpv else ''}.",
            {"strategy": None},
        )

    snap = snapshot_row(strategy) or {}
    mode = strategy.mode
    answer = (
        f"Strategia {mode}: {strategy.primary_metric} "
        f"target {float(strategy.primary_target):.4g} "
        f"({float(strategy.primary_weight):.0f}% peso)."
    )
    if mode != "single" and strategy.secondary_metric:
        answer += (
            f" Secondaria {strategy.secondary_metric} "
            f"{float(strategy.secondary_target or 0):.4g} "
            f"({float(strategy.secondary_weight or 0):.0f}%)."
        )
    if mode == "blended_3" and strategy.tertiary_metric:
        answer += (
            f" Terziaria {strategy.tertiary_metric} "
            f"({float(strategy.tertiary_weight or 0):.0f}%)."
        )
    return answer, {"strategy": snap}


READERS: dict[str, Any] = {
    "dashboard.read": get_dashboard,
    "run.last": get_last_run,
    "run.history": get_run_history,
    "decision.list": get_term_decisions,
    "decision.explain": explain_decision,
    "proposal.list": list_proposals_query,
    "proposal.detail": get_proposal_detail,
    "strategy.read": get_strategy,
}


async def run_query_reader(
    db: AsyncSession,
    *,
    tenant_id: str,
    line_item_id: str,
    intent: str,
    payload: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    fn = READERS.get(intent)
    if fn is None:
        raise ValueError(f"Query intent sconosciuto: {intent}")
    pl = dict(payload or {})
    pl.pop("line_item_id", None)
    return await fn(db, tenant_id=tenant_id, line_item_id=line_item_id, **pl)


def help_answer() -> tuple[str, dict[str, Any]]:
    text = (
        "Posso leggere dashboard, ultime run, decisioni e strategia; "
        "lanciare Setup Agent (configurazione) o Tuning Agent (micro-fix); "
        "approvare, applicare, rifiutare o revertare proposte. "
        "Esempi: «Come va la campagna?», «Il CPA è alto, sistemalo», "
        "«Approva la proposta pending»."
    )
    return text, {"capabilities": ["query", "brief", "govern"]}


def can_revert_proposal(prop: AgentProposal) -> bool:
    if prop.status != "applied" or prop.applied_at is None:
        return False
    return utcnow() - prop.applied_at <= timedelta(days=7)
