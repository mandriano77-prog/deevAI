"""Run-level decision counters — single source of truth.

The :class:`~deevai_api.models.Run` row carries a handful of
denormalized counters (``n_terms_evaluated``, ``n_terms_changed``,
``n_terms_boosted``, ``n_terms_cut``, ``n_terms_zeroed``) that the
reporting layer surfaces to the dashboard. Two call sites compute
them:

1. The scheduler, *at run-commit time*, so the counters land in the
   row from the start (fast path for the UI).
2. The reporting service, *lazily*, when an older Run row has the
   counters still ``NULL`` — a transient fallback while the backfill
   script catches up.

Both paths route through :func:`compute_run_counters` so the
definition of \"changed / boosted / cut / zeroed\" can only ever live
in one place. Anything iterable of objects with
``previous_modifier`` / ``new_modifier`` works, which is enough for
both the ORM-backed and the in-memory cases.
"""

from __future__ import annotations

from typing import Iterable, Protocol


class _ModifierPair(Protocol):
    """Structural type for anything that exposes the two modifiers.

    Both the ORM :class:`Decision` row and SQLAlchemy ``Row`` tuples
    cast to namedtuples qualify.
    """

    previous_modifier: object  # Numeric -> Decimal in practice
    new_modifier: object


def compute_run_counters(decisions: Iterable[_ModifierPair]) -> dict[str, int]:
    """Aggregate the per-Run decision counters from a sequence of decisions.

    Parameters
    ----------
    decisions:
        Any iterable whose items expose ``previous_modifier`` and
        ``new_modifier`` (ORM Decision rows, bare tuples through a
        small adapter, etc.). Values are coerced to ``float`` so
        Decimal columns work transparently.

    Returns
    -------
    dict with keys: ``n_terms_evaluated``, ``n_terms_changed``,
    ``n_terms_boosted``, ``n_terms_cut``, ``n_terms_zeroed``.

    Semantics
    ---------
    * ``evaluated`` — every decision the engine produced for the run.
    * ``boosted`` / ``cut`` — strict inequality on the modifier.
      ``boosted`` and ``cut`` are mutually exclusive and both count as
      ``changed``.
    * ``zeroed`` — the new modifier landed exactly on ``0.0``,
      regardless of the previous value. A term cut to zero counts as
      both ``cut`` and ``zeroed``. This matches the existing fallback
      in :mod:`services.reporting`.
    """
    evaluated = 0
    changed = 0
    boosted = 0
    cut = 0
    zeroed = 0

    for d in decisions:
        evaluated += 1
        prev_f = float(d.previous_modifier)
        new_f = float(d.new_modifier)
        if new_f == 0.0:
            zeroed += 1
        if new_f > prev_f:
            boosted += 1
            changed += 1
        elif new_f < prev_f:
            cut += 1
            changed += 1

    return {
        "n_terms_evaluated": evaluated,
        "n_terms_changed": changed,
        "n_terms_boosted": boosted,
        "n_terms_cut": cut,
        "n_terms_zeroed": zeroed,
    }


__all__ = ["compute_run_counters"]
