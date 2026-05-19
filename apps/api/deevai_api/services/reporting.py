"""Reporting service — read-only aggregations for the dashboard.

The reporting layer is intentionally **pure read**: every function takes
an ``AsyncSession`` plus the resolved ``tenant_id`` and returns DTOs.
No mutation, no side-effects, no DSP calls. Safe under DSP_DRY_RUN and
safe to call from any route protected by ``get_current_user_claims``.

Authorization model: callers MUST resolve ``tenant_id`` from JWT claims
before invoking these functions. Every query is filtered on
``tenant_id`` and additionally checks ownership of the targeted Run /
LineItem so that a cross-tenant ID guess yields ``None`` rather than
leaking data.
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Decision, LineItem, Run
from ..schemas.reporting import (
    ConstraintEventDTO,
    DecisionDistribution,
    MoverDTO,
    RunKpiBlock,
    RunSummaryDTO,
)
from .run_stats import compute_run_counters

# Matches the canonical note shape written by
# packages/bidagent/decision_engine.py::_apply_constraint_policy.
_CONSTRAINT_NOTE_RE = re.compile(
    r"^constraint_violated_(?P<metric>[a-z_]+):\s+"
    r"observed\s+(?P<observed>-?\d+(?:\.\d+)?)\s+"
    r"(?P<operator>[a-z]+)\s+"
    r"(?P<threshold>-?\d+(?:\.\d+)?)\s*"
    r"\((?P<policy>[a-z]+)\)\s*$"
)


# --------------------------------------------------------------- helpers


def _as_float(value: object) -> Optional[float]:
    """SQLAlchemy hands us Decimals on Numeric columns; collapse to float."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _compute_kpis(run: Run) -> RunKpiBlock:
    spend = _as_float(run.blended_spend)
    impressions = run.blended_impressions
    clicks = run.blended_clicks
    conversions = run.blended_visits

    ctr = _safe_div(
        float(clicks) if clicks is not None else None,
        float(impressions) if impressions else None,
    )
    cpm = None
    if spend is not None and impressions:
        cpm = 1000.0 * spend / impressions
    cpa = _safe_div(
        spend,
        float(conversions) if conversions else None,
    )

    return RunKpiBlock(
        spend=spend,
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        ctr=ctr,
        cpm=cpm,
        cpa=cpa,
        roas=_as_float(run.blended_roas),
        cpv_target=_as_float(run.blended_cpv_target),
        cpv_observed=_as_float(run.blended_cpv_observed),
    )


async def _compute_distribution(
    db: AsyncSession, run: Run,
) -> DecisionDistribution:
    """Use denormalized Run counters when present, else aggregate live."""
    if run.n_terms_evaluated is not None:
        return DecisionDistribution(
            n_terms_evaluated=run.n_terms_evaluated,
            n_terms_changed=run.n_terms_changed or 0,
            n_terms_boosted=run.n_terms_boosted or 0,
            n_terms_cut=run.n_terms_cut or 0,
            n_terms_zeroed=run.n_terms_zeroed or 0,
        )

    # Live aggregation — counts straight from `decisions`. Routed
    # through ``compute_run_counters`` so the semantics stay aligned
    # with the scheduler's commit-time path.
    rows = (
        await db.execute(
            select(Decision.previous_modifier, Decision.new_modifier).where(
                Decision.run_id == run.id,
                Decision.tenant_id == run.tenant_id,
            )
        )
    ).all()

    class _Pair:
        __slots__ = ("previous_modifier", "new_modifier")

        def __init__(self, prev: object, new: object) -> None:
            self.previous_modifier = prev
            self.new_modifier = new

    counters = compute_run_counters(_Pair(prev, new) for prev, new in rows)
    return DecisionDistribution(**counters)


def _parse_constraint_note(note: Optional[str]) -> dict[str, Optional[str]]:
    """Extract metric/observed/operator/threshold/policy from the engine note."""
    if not note:
        return {}
    m = _CONSTRAINT_NOTE_RE.match(note.strip())
    if not m:
        return {}
    return {
        "metric": m.group("metric"),
        "observed": m.group("observed"),
        "operator": m.group("operator"),
        "threshold": m.group("threshold"),
        "policy": m.group("policy"),
    }


# -------------------------------------------------------------- public API


async def get_run(
    db: AsyncSession, *, run_id: str, tenant_id: str,
) -> Optional[Run]:
    """Tenant-scoped fetch. Returns None for not-found OR cross-tenant."""
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != tenant_id:
        return None
    return run


async def get_run_summary(
    db: AsyncSession, *, run_id: str, tenant_id: str,
) -> Optional[RunSummaryDTO]:
    """Top-line KPIs + decision distribution for one run."""
    run = await get_run(db, run_id=run_id, tenant_id=tenant_id)
    if run is None:
        return None

    kpis = _compute_kpis(run)
    distribution = await _compute_distribution(db, run)

    return RunSummaryDTO(
        run_id=run.id,
        line_item_id=run.line_item_id,
        week_label=run.week_label,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        window_start=run.window_start,
        window_end=run.window_end,
        kpis=kpis,
        distribution=distribution,
        digest_text=run.digest_text,
    )


async def get_top_movers(
    db: AsyncSession,
    *,
    run_id: str,
    tenant_id: str,
    limit: int = 10,
) -> list[MoverDTO]:
    """The N decisions with the largest absolute modifier delta.

    Ordering is done in Python so we can compute ``abs(delta)`` without
    relying on Postgres-specific functions on a Numeric column. The
    candidate set is bounded by ``run_id`` so this is always small."""
    if limit <= 0:
        return []

    # Verify the run belongs to the tenant first (avoid leaking the
    # existence of someone else's run via an empty array).
    run = await get_run(db, run_id=run_id, tenant_id=tenant_id)
    if run is None:
        return []

    rows = (
        await db.execute(
            select(Decision).where(
                Decision.run_id == run_id,
                Decision.tenant_id == tenant_id,
            )
        )
    ).scalars().all()

    movers: list[MoverDTO] = []
    for d in rows:
        prev = float(d.previous_modifier)
        new = float(d.new_modifier)
        delta = new - prev
        movers.append(
            MoverDTO(
                decision_id=d.id,
                targeting_module=d.targeting_module,
                targeting_key=d.targeting_key,
                value=d.value,
                field_label=d.field_label,
                old_modifier=prev,
                new_modifier=new,
                delta=delta,
                abs_delta=abs(delta),
                reason=d.reason,
                note=d.note,
                status=d.status,
            )
        )

    movers.sort(key=lambda m: (-m.abs_delta, m.decision_id))
    return movers[:limit]


async def get_constraint_events(
    db: AsyncSession,
    *,
    run_id: str,
    tenant_id: str,
) -> list[ConstraintEventDTO]:
    """Every Decision whose engine reason was a hard-constraint hit."""
    run = await get_run(db, run_id=run_id, tenant_id=tenant_id)
    if run is None:
        return []

    rows = (
        await db.execute(
            select(Decision)
            .where(
                Decision.run_id == run_id,
                Decision.tenant_id == tenant_id,
                Decision.reason == "constraint_violated",
            )
            .order_by(Decision.created_at)
        )
    ).scalars().all()

    events: list[ConstraintEventDTO] = []
    for d in rows:
        parsed = _parse_constraint_note(d.note)
        observed = parsed.get("observed")
        threshold = parsed.get("threshold")
        events.append(
            ConstraintEventDTO(
                decision_id=d.id,
                targeting_module=d.targeting_module,
                targeting_key=d.targeting_key,
                value=d.value,
                field_label=d.field_label,
                old_modifier=float(d.previous_modifier),
                new_modifier=float(d.new_modifier),
                metric=parsed.get("metric"),
                observed=float(observed) if observed is not None else None,
                operator=parsed.get("operator"),
                threshold=float(threshold) if threshold is not None else None,
                policy=parsed.get("policy"),
                raw_note=d.note,
            )
        )
    return events


async def get_line_item_run_summaries(
    db: AsyncSession,
    *,
    line_item_id: str,
    tenant_id: str,
    limit: int = 20,
) -> list[RunSummaryDTO]:
    """Last N run summaries for a line item, newest first.

    Returns an empty list for unknown or cross-tenant line items
    (rather than raising — the router converts 'no line item' into
    404 separately if needed)."""
    if limit <= 0:
        return []

    # Existence + tenant check on the line item itself.
    line_item = await db.get(LineItem, line_item_id)
    if line_item is None or line_item.tenant_id != tenant_id:
        return []

    runs = (
        await db.execute(
            select(Run)
            .where(
                Run.line_item_id == line_item_id,
                Run.tenant_id == tenant_id,
            )
            .order_by(desc(Run.started_at))
            .limit(limit)
        )
    ).scalars().all()

    summaries: list[RunSummaryDTO] = []
    for run in runs:
        kpis = _compute_kpis(run)
        distribution = await _compute_distribution(db, run)
        summaries.append(
            RunSummaryDTO(
                run_id=run.id,
                line_item_id=run.line_item_id,
                week_label=run.week_label,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                window_start=run.window_start,
                window_end=run.window_end,
                kpis=kpis,
                distribution=distribution,
                digest_text=run.digest_text,
            )
        )
    return summaries


async def line_item_exists_for_tenant(
    db: AsyncSession, *, line_item_id: str, tenant_id: str,
) -> bool:
    """Lightweight existence check used by the router for 404 vs empty."""
    result = await db.execute(
        select(func.count())
        .select_from(LineItem)
        .where(
            LineItem.id == line_item_id,
            LineItem.tenant_id == tenant_id,
        )
    )
    return (result.scalar() or 0) > 0


__all__ = [
    "get_run_summary",
    "get_top_movers",
    "get_constraint_events",
    "get_line_item_run_summaries",
    "line_item_exists_for_tenant",
]
