"""One-shot: line items without strategy get tenant-default single CPV strategy.

Usage (from apps/api):
    uv run python scripts/backfill_line_item_strategies.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deevai_api.models import LineItem, OptimizationStrategy  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def backfill(session: AsyncSession) -> int:
    created = 0
    items = (await session.execute(select(LineItem))).scalars().all()
    for item in items:
        existing = (
            await session.execute(
                select(OptimizationStrategy).where(
                    OptimizationStrategy.tenant_id == item.tenant_id,
                    OptimizationStrategy.line_item_id == item.id,
                ),
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        row = OptimizationStrategy(
            tenant_id=item.tenant_id,
            line_item_id=item.id,
            mode="single",
            primary_metric="cpv",
            primary_target=float(item.cpv_target or 0.5),
            primary_weight=100,
            tolerance_band=0.2,
            status="active",
        )
        session.add(row)
        created += 1
    await session.commit()
    return created


async def main() -> None:
    engine = create_async_engine(_database_url(), pool_pre_ping=True)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        n = await backfill(session)
    await engine.dispose()
    print(f"Created {n} line-item optimization strategies")


if __name__ == "__main__":
    asyncio.run(main())
