"""Seed the founder's tenant — runs once on a fresh DB.

Creates:
  - Tenant 'kiliagon' (you)
  - User 'adriano' (owner)
  - Setting row with defaults
  - Sets observation_only_until to 14 days from now

Usage (from apps/api/, with venv active and .env loaded):

    python -m deevai_api.scripts.seed_first_tenant
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import timedelta

from sqlalchemy import select

from ..db import session_scope
from ..models import Setting, Tenant, User, utcnow

log = logging.getLogger(__name__)
logging.basicConfig(level="INFO", format="%(levelname)s  %(message)s")


SLUG = "kiliagon"
TENANT_NAME = "Kiliagon"
USER_EMAIL = "adriano@deevai.local"   # placeholder — replace in real signup
USER_NAME = "Adriano"


async def main() -> int:
    async with session_scope() as db:
        # Idempotency — skip if already present
        existing = (await db.execute(
            select(Tenant).where(Tenant.slug == SLUG)
        )).scalar_one_or_none()
        if existing is not None:
            log.info("Tenant '%s' already exists (id=%s). Nothing to do.", SLUG, existing.id)
            print(f"X-Tenant-Id: {existing.id}")
            return 0

        tenant = Tenant(name=TENANT_NAME, slug=SLUG, plan="beta", status="active")
        db.add(tenant)
        await db.flush()

        user = User(
            tenant_id=tenant.id,
            email=USER_EMAIL,
            name=USER_NAME,
            role="owner",
            status="active",
        )
        db.add(user)

        observation_until = utcnow() + timedelta(days=14)
        setting = Setting(
            tenant_id=tenant.id,
            default_cpv_target=0.40,
            observation_only_until=observation_until,
            digest_language="it",
        )
        db.add(setting)

        log.info("✓ Tenant created: id=%s slug=%s", tenant.id, tenant.slug)
        log.info("✓ User created:   id=%s email=%s", user.id, user.email)
        log.info("✓ Settings:       cpv_target=%.2f observation_until=%s",
                 setting.default_cpv_target, observation_until.isoformat())
        print()
        print("Use this in API requests until auth is wired (Sprint 1.4):")
        print(f"  X-Tenant-Id: {tenant.id}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
