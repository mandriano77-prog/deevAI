"""One-shot: populate denormalized Run reporting counters.

Iterates every ``Run`` whose ``n_terms_evaluated`` is still ``NULL``
(i.e. created before the scheduler started computing the counters at
commit time) and fills the five ``n_terms_*`` columns from the live
:class:`Decision` rows. Safe to re-run — already-populated runs are
skipped because the WHERE clause excludes them.

Usage (from ``apps/api``)::

    DATABASE_URL=postgresql://… uv run python scripts/backfill_run_counters.py

Output: one log line per batch + a final summary with the total
number of runs updated.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deevai_api.models import Decision, Run  # noqa: E402
from deevai_api.services.run_stats import compute_run_counters  # noqa: E402

BATCH_SIZE = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("backfill_run_counters")


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def backfill(session: AsyncSession, *, batch_size: int = BATCH_SIZE) -> int:
    """Populate ``n_terms_*`` counters for every Run still missing them.

    Returns the total number of runs updated. Idempotent.
    """
    total = 0
    while True:
        # Fetch a bounded batch so memory stays flat on huge tables.
        runs = (
            await session.execute(
                select(Run)
                .where(Run.n_terms_evaluated.is_(None))
                .order_by(Run.id)
                .limit(batch_size)
            )
        ).scalars().all()

        if not runs:
            break

        for run in runs:
            decisions = (
                await session.execute(
                    select(
                        Decision.previous_modifier, Decision.new_modifier,
                    ).where(
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

            counters = compute_run_counters(_Pair(p, n) for p, n in decisions)
            run.n_terms_evaluated = counters["n_terms_evaluated"]
            run.n_terms_changed = counters["n_terms_changed"]
            run.n_terms_boosted = counters["n_terms_boosted"]
            run.n_terms_cut = counters["n_terms_cut"]
            run.n_terms_zeroed = counters["n_terms_zeroed"]
            total += 1

        await session.commit()
        log.info(
            "Backfilled %d runs (running total: %d)", len(runs), total,
        )

    return total


async def main() -> None:
    engine = create_async_engine(_database_url(), pool_pre_ping=True)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        n = await backfill(session)
    await engine.dispose()
    log.info("Done. Updated %d run row(s).", n)
    print(f"Updated {n} run row(s)")


if __name__ == "__main__":
    asyncio.run(main())
