"""Print the demo tenant id (if any) to stdout.

Useful one-off helper for setting the ``DEMO_TENANT_ID`` env var on
hosted environments (Render etc.) where direct psql access is blocked
by an IP allow-list. Run via the platform's "job" / one-off command
runner — the service container already has DB credentials in
``DATABASE_URL``.

Usage (local):
    cd apps/api && .venv/bin/python -m scripts.print_demo_tenant_id

Usage (Render):
    render jobs create <service-id> \\
        --start-command "python -m scripts.print_demo_tenant_id"
    # then read DEMO_TENANT_ID=<uuid> from the job logs
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _async_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.stderr.write("DATABASE_URL not set in env\n")
        sys.exit(2)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def _main() -> None:
    engine = create_async_engine(_async_database_url())
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT id::text, name, slug FROM tenants "
                    "WHERE is_demo = true ORDER BY created_at LIMIT 1"
                )
            )
            row = result.first()
            if row is None:
                print("NO_DEMO_TENANT")
                sys.exit(1)
            print(f"DEMO_TENANT_ID={row[0]}")
            print(f"name={row[1]}")
            print(f"slug={row[2]}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
