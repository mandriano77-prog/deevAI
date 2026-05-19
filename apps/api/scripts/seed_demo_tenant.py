"""Seed the synthetic ``Demo Tenant`` used for sales / pitch / self-serve previews.

Run::

    cd apps/api && .venv/bin/python -m scripts.seed_demo_tenant

The script is **idempotent**: running it twice (or twenty times) converges to
the same state — we use stable UUIDs derived from a fixed namespace and
``upsert`` semantics for every row. Re-running on a populated tenant updates
existing rows in place; it never duplicates Runs / Decisions.

What gets created
-----------------
* 1 Tenant            ``Demo Tenant`` / slug ``demo`` / plan ``demo`` / ``is_demo=True``
* 1 User              ``demo@deevai.app`` (bcrypt-hashed password ``DemoDeevAI!2026``)
* 1 Integration       fake DV360 seat in ``connected`` status (no real OAuth)
* 1 Advertiser        ``Demo Brand IT``
* 3 LineItems         realistic Q2 brand / performance / CTV names
* 4 Runs per LI       last 4 Mondays, w/ blended KPIs + reporting counters
* 15-30 Decisions     spread over all 6 levers (time / platform / device /
                      geo / inventory / audience) with mixed reasons
* 0-2 violation notes prefixed ``constraint_violated_…`` per Run
* 1 OptimizationStrategy (tenant-default) + 2 HardConstraints (CPA ≤ 8 ; ROAS ≥ 2)

Determinism
-----------
``random.seed(42)`` at the top of the run; every Run / Decision / metric is
generated from the seeded RNG. The tenant id is a deterministic UUIDv5 derived
from the seed namespace, so external systems pinned to ``DEMO_TENANT_ID`` see
the same id across rebuilds.

Safe to run in production. The script only touches rows whose id matches the
deterministic seed UUIDs (or upserts a Tenant by primary key).
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Make ``deevai_api`` importable when running as ``python -m scripts.seed_demo_tenant``
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deevai_api.config import get_settings  # noqa: E402
from deevai_api.models import (  # noqa: E402
    Advertiser,
    Decision,
    HardConstraint,
    Integration,
    LineItem,
    OptimizationStrategy,
    Run,
    Setting,
    Tenant,
    User,
)
from deevai_api.services.auth import hash_password  # noqa: E402

# ---------------------------------------------------------------------------
# Stable identifiers — UUIDv5 means re-running the seed lands on the same rows.
# ---------------------------------------------------------------------------
_DEMO_NAMESPACE = uuid.UUID("11111111-2222-3333-4444-555555555555")
DEMO_TENANT_ID = str(uuid.uuid5(_DEMO_NAMESPACE, "tenant:demo"))
DEMO_USER_ID = str(uuid.uuid5(_DEMO_NAMESPACE, "user:demo@deevai.app"))
DEMO_INTEGRATION_ID = str(uuid.uuid5(_DEMO_NAMESPACE, "integration:demo-dv360"))
DEMO_ADVERTISER_ID = str(uuid.uuid5(_DEMO_NAMESPACE, "advertiser:demo-brand"))
DEMO_SETTING_ID = str(uuid.uuid5(_DEMO_NAMESPACE, "setting:demo"))
DEMO_STRATEGY_ID = str(uuid.uuid5(_DEMO_NAMESPACE, "strategy:demo-default"))

DEMO_PASSWORD = "DemoDeevAI!2026"

DEMO_LINE_ITEMS: list[dict[str, object]] = [
    {
        "id": str(uuid.uuid5(_DEMO_NAMESPACE, "li:brand-awareness-q2")),
        "name": "Brand Awareness Q2",
        "amazon_line_item_id": "dv360-li-brand-awareness-q2",
        "cpv_target": Decimal("0.45"),
        # Brand campaigns tend to overspend a touch — helpful for the demo
        # narrative ("look, deevAI throttled CPM here").
        "ctr_band": (0.0030, 0.0055),
        "cpm_band": (Decimal("5.50"), Decimal("9.00")),
        "spend_band": (Decimal("4200"), Decimal("6800")),
    },
    {
        "id": str(uuid.uuid5(_DEMO_NAMESPACE, "li:performance-retargeting-eu")),
        "name": "Performance Retargeting EU",
        "amazon_line_item_id": "dv360-li-performance-retargeting-eu",
        "cpv_target": Decimal("0.28"),
        "ctr_band": (0.0055, 0.0080),
        "cpm_band": (Decimal("3.20"), Decimal("6.00")),
        "spend_band": (Decimal("2800"), Decimal("4400")),
    },
    {
        "id": str(uuid.uuid5(_DEMO_NAMESPACE, "li:prospecting-ctv-it")),
        "name": "Prospecting CTV IT",
        "amazon_line_item_id": "dv360-li-prospecting-ctv-it",
        "cpv_target": Decimal("0.62"),
        "ctr_band": (0.0035, 0.0070),
        "cpm_band": (Decimal("7.80"), Decimal("12.00")),
        "spend_band": (Decimal("3600"), Decimal("5200")),
    },
]

# All 6 levers exposed by the bidagent (Sprint 0). The seed sprinkles
# Decisions across every lever so the reporting UI's stacked-bar lights up.
LEVERS: Sequence[tuple[str, list[tuple[str, str]]]] = (
    (
        "time",
        [
            ("dayparting", "Mon 06-09"),
            ("dayparting", "Mon 18-21"),
            ("dayparting", "Sat 12-15"),
            ("dayparting", "Sun 21-24"),
        ],
    ),
    (
        "platform",
        [
            ("os", "iOS"),
            ("os", "Android"),
            ("os", "Windows"),
            ("os", "macOS"),
        ],
    ),
    (
        "device",
        [
            ("device_type", "mobile"),
            ("device_type", "desktop"),
            ("device_type", "tablet"),
            ("device_type", "connected_tv"),
        ],
    ),
    (
        "geo",
        [
            ("region", "Lombardia"),
            ("region", "Lazio"),
            ("region", "Veneto"),
            ("region", "Campania"),
            ("region", "Piemonte"),
        ],
    ),
    (
        "inventory",
        [
            ("exchange", "Google AdX"),
            ("exchange", "Magnite"),
            ("exchange", "PubMatic"),
            ("site", "corriere.it"),
            ("site", "repubblica.it"),
        ],
    ),
    (
        "audience",
        [
            ("affinity", "Auto Enthusiasts"),
            ("affinity", "Travel Buffs"),
            ("in_market", "Compact Cars"),
            ("in_market", "Family Vacations"),
            ("custom", "Lookalike CRM Top10%"),
        ],
    ),
)

REASONS = [
    "under_target",
    "over_target",
    "on_target",
    "insufficient_volume",
    "anomalous_ctr",
    "low_viewability",
    "zero_visits",
    "exploration_revive",
    "smoothed",
]

VIOLATION_PREFIXES = (
    "constraint_violated_cpa_above_threshold",
    "constraint_violated_roas_below_floor",
)


def _monday_of_week(reference: datetime, weeks_back: int) -> datetime:
    """Return the Monday 00:00 UTC of ``reference - weeks_back`` weeks."""
    base = reference - timedelta(weeks=weeks_back)
    monday = base - timedelta(days=base.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


async def _upsert_tenant(db: AsyncSession) -> Tenant:
    tenant = await db.get(Tenant, DEMO_TENANT_ID)
    if tenant is None:
        tenant = Tenant(
            id=DEMO_TENANT_ID,
            name="Demo Tenant",
            slug="demo",
            plan="demo",
            status="active",
            is_demo=True,
        )
        db.add(tenant)
    else:
        tenant.name = "Demo Tenant"
        tenant.slug = "demo"
        tenant.plan = "demo"
        tenant.status = "active"
        tenant.is_demo = True
    await db.flush()
    return tenant


async def _upsert_user(db: AsyncSession, tenant_id: str) -> User:
    user = await db.get(User, DEMO_USER_ID)
    password_hash = hash_password(DEMO_PASSWORD)
    if user is None:
        user = User(
            id=DEMO_USER_ID,
            tenant_id=tenant_id,
            email="demo@deevai.app",
            name="Demo User",
            password_hash=password_hash,
            role="owner",
            status="active",
        )
        db.add(user)
    else:
        user.tenant_id = tenant_id
        user.email = "demo@deevai.app"
        user.name = "Demo User"
        # Only rotate the hash if it's missing — bcrypt is non-deterministic,
        # so re-hashing every run would change the column for no reason.
        if not user.password_hash:
            user.password_hash = password_hash
        user.role = "owner"
        user.status = "active"
    await db.flush()
    return user


async def _upsert_setting(db: AsyncSession, tenant_id: str) -> Setting:
    existing = await db.scalar(select(Setting).where(Setting.tenant_id == tenant_id))
    if existing is None:
        setting = Setting(
            id=DEMO_SETTING_ID,
            tenant_id=tenant_id,
            default_cpv_target=0.50,
            digest_language="it",
            default_line_item_mode="approval_required",
        )
        db.add(setting)
        await db.flush()
        return setting
    return existing


async def _upsert_integration(db: AsyncSession, tenant_id: str) -> Integration:
    integration = await db.get(Integration, DEMO_INTEGRATION_ID)
    if integration is None:
        integration = Integration(
            id=DEMO_INTEGRATION_ID,
            tenant_id=tenant_id,
            provider="dv360",
            name="DV360 — Demo Seat",
            client_id="demo-oauth-client-id",
            status="connected",
            provider_config={
                "advertiser_id": "demo-advertiser-1234567",
                "partner_id": "demo-partner-9876543",
                "synthetic": True,
            },
        )
        # client_secret / refresh_token left empty — the demo never talks to
        # Google. We deliberately keep the encrypted columns NULL.
        db.add(integration)
    else:
        integration.tenant_id = tenant_id
        integration.provider = "dv360"
        integration.name = "DV360 — Demo Seat"
        integration.status = "connected"
        integration.provider_config = {
            "advertiser_id": "demo-advertiser-1234567",
            "partner_id": "demo-partner-9876543",
            "synthetic": True,
        }
    await db.flush()
    return integration


async def _upsert_advertiser(
    db: AsyncSession, tenant_id: str, integration_id: str
) -> Advertiser:
    advertiser = await db.get(Advertiser, DEMO_ADVERTISER_ID)
    if advertiser is None:
        advertiser = Advertiser(
            id=DEMO_ADVERTISER_ID,
            tenant_id=tenant_id,
            integration_id=integration_id,
            amazon_advertiser_id="demo-advertiser-1234567",
            name="Demo Brand IT",
            currency="EUR",
            country="IT",
            status="active",
        )
        db.add(advertiser)
    else:
        advertiser.tenant_id = tenant_id
        advertiser.integration_id = integration_id
        advertiser.amazon_advertiser_id = "demo-advertiser-1234567"
        advertiser.name = "Demo Brand IT"
        advertiser.currency = "EUR"
        advertiser.country = "IT"
        advertiser.status = "active"
    await db.flush()
    return advertiser


async def _upsert_line_items(
    db: AsyncSession, tenant_id: str, advertiser_id: str
) -> list[LineItem]:
    items: list[LineItem] = []
    for spec in DEMO_LINE_ITEMS:
        li = await db.get(LineItem, spec["id"])
        if li is None:
            li = LineItem(
                id=spec["id"],  # type: ignore[arg-type]
                tenant_id=tenant_id,
                advertiser_id=advertiser_id,
                amazon_line_item_id=spec["amazon_line_item_id"],  # type: ignore[arg-type]
                name=spec["name"],  # type: ignore[arg-type]
                cpv_target=spec["cpv_target"],  # type: ignore[arg-type]
                current_max_bid=Decimal("1.20"),
                mode="approval_required",
                status="active",
            )
            db.add(li)
        else:
            li.tenant_id = tenant_id
            li.advertiser_id = advertiser_id
            li.amazon_line_item_id = spec["amazon_line_item_id"]  # type: ignore[arg-type]
            li.name = spec["name"]  # type: ignore[arg-type]
            li.cpv_target = spec["cpv_target"]  # type: ignore[arg-type]
            li.mode = "approval_required"
            li.status = "active"
        items.append(li)
    await db.flush()
    return items


async def _upsert_strategy_and_constraints(
    db: AsyncSession, tenant_id: str
) -> OptimizationStrategy:
    strategy = await db.get(OptimizationStrategy, DEMO_STRATEGY_ID)
    if strategy is None:
        strategy = OptimizationStrategy(
            id=DEMO_STRATEGY_ID,
            tenant_id=tenant_id,
            line_item_id=None,  # tenant-default
            mode="blended_2",
            primary_metric="cpa",
            primary_target=Decimal("7.50"),
            primary_weight=Decimal("70.00"),
            secondary_metric="roas",
            secondary_target=Decimal("2.50"),
            secondary_weight=Decimal("30.00"),
            tolerance_band=Decimal("0.20"),
            status="active",
        )
        db.add(strategy)
    else:
        strategy.tenant_id = tenant_id
        strategy.line_item_id = None
        strategy.mode = "blended_2"
        strategy.primary_metric = "cpa"
        strategy.primary_target = Decimal("7.50")
        strategy.primary_weight = Decimal("70.00")
        strategy.secondary_metric = "roas"
        strategy.secondary_target = Decimal("2.50")
        strategy.secondary_weight = Decimal("30.00")
        strategy.tolerance_band = Decimal("0.20")
        strategy.status = "active"
    await db.flush()

    # Replace existing constraints wholesale — there are at most 2, so this
    # delete+insert is cheaper than diffing.
    await db.execute(
        delete(HardConstraint).where(
            HardConstraint.optimization_strategy_id == strategy.id
        )
    )
    db.add(
        HardConstraint(
            id=str(uuid.uuid5(_DEMO_NAMESPACE, "constraint:cpa-le-8")),
            tenant_id=tenant_id,
            optimization_strategy_id=strategy.id,
            metric="cpa",
            operator="lte",
            value=Decimal("8.00"),
            violation_policy="freeze",
            status="active",
        )
    )
    db.add(
        HardConstraint(
            id=str(uuid.uuid5(_DEMO_NAMESPACE, "constraint:roas-ge-2")),
            tenant_id=tenant_id,
            optimization_strategy_id=strategy.id,
            metric="roas",
            operator="gte",
            value=Decimal("2.00"),
            violation_policy="alert",
            status="active",
        )
    )
    await db.flush()
    return strategy


def _make_run_id(line_item_id: str, weeks_back: int) -> str:
    return str(uuid.uuid5(_DEMO_NAMESPACE, f"run:{line_item_id}:{weeks_back}"))


def _make_decision_id(run_id: str, idx: int) -> str:
    return str(uuid.uuid5(_DEMO_NAMESPACE, f"decision:{run_id}:{idx}"))


def _round_decimal(value: Decimal, places: int) -> Decimal:
    quant = Decimal(10) ** -places
    return value.quantize(quant)


def _decision_note(lever: str, reason: str, value: str) -> str:
    """Hand-rolled, slightly varied Italian copy — makes the demo UI feel alive."""
    snippets = {
        "under_target": f"CPV sotto target su {value}: alziamo il modifier per spingere il volume.",
        "over_target": f"CPV oltre il tetto su {value}: tagliamo del 20–30%.",
        "on_target": f"Performance in linea su {value}: nessuna azione richiesta.",
        "insufficient_volume": f"Volume troppo basso su {value} ({lever}): in attesa di più dati.",
        "anomalous_ctr": f"CTR anomalo rilevato su {value}: degradiamo il modifier in attesa di verifica.",
        "low_viewability": f"Viewability < 60% su {value}: riduciamo il bid.",
        "zero_visits": f"Zero visite negli ultimi 7gg su {value}: zero-out e revival fra 14gg.",
        "exploration_revive": f"Riattiviamo {value} dopo zero-out: budget di esplorazione 5%.",
        "smoothed": f"Smoothed: variazione clippata a ±50% rispetto alla settimana scorsa.",
    }
    return snippets.get(reason, f"Decision su {lever}/{value} — reason={reason}.")


async def _seed_runs_and_decisions(
    db: AsyncSession,
    tenant_id: str,
    line_items: list[LineItem],
    rng: random.Random,
) -> tuple[int, int]:
    """Upsert 4 Runs per LineItem + 15-30 Decisions per Run. Returns (runs, decisions)."""
    now = datetime.now(timezone.utc)
    n_runs = 0
    n_decisions = 0

    for li in line_items:
        spec = next(s for s in DEMO_LINE_ITEMS if s["id"] == li.id)
        ctr_lo, ctr_hi = spec["ctr_band"]  # type: ignore[misc]
        cpm_lo, cpm_hi = spec["cpm_band"]  # type: ignore[misc]
        spend_lo, spend_hi = spec["spend_band"]  # type: ignore[misc]

        for weeks_back in range(4, 0, -1):
            run_id = _make_run_id(li.id, weeks_back)
            window_start = _monday_of_week(now, weeks_back)
            window_end = window_start + timedelta(days=7)
            week_label = f"W{window_start.isocalendar().week:02d}-{window_start.year}"

            # Plausible KPIs — deterministic via the seeded RNG.
            spend = _round_decimal(
                Decimal(str(rng.uniform(float(spend_lo), float(spend_hi)))), 2
            )
            cpm = _round_decimal(
                Decimal(str(rng.uniform(float(cpm_lo), float(cpm_hi)))), 2
            )
            impressions = int((spend / cpm) * Decimal(1000))
            ctr = rng.uniform(ctr_lo, ctr_hi)
            clicks = int(impressions * ctr)
            # Conversions: ~ 2.5-6% of clicks for these synthetic LIs.
            conversions = max(1, int(clicks * rng.uniform(0.025, 0.060)))
            roas = _round_decimal(Decimal(str(rng.uniform(1.80, 3.40))), 4)

            # Reporting counters — mirror the Sprint 0 denormalized fields.
            n_eval = rng.randint(80, 160)
            n_changed = rng.randint(15, 35)
            n_boosted = rng.randint(3, max(4, n_changed // 2))
            n_cut = rng.randint(3, max(4, n_changed - n_boosted - 1))
            n_zeroed = max(0, n_changed - n_boosted - n_cut)

            run = await db.get(Run, run_id)
            if run is None:
                run = Run(
                    id=run_id,
                    tenant_id=tenant_id,
                    line_item_id=li.id,
                    week_label=week_label,
                    window_start=window_start,
                    window_end=window_end,
                    status="succeeded",
                    started_at=window_end,
                    completed_at=window_end + timedelta(minutes=12),
                )
                db.add(run)
            run.tenant_id = tenant_id
            run.line_item_id = li.id
            run.week_label = week_label
            run.window_start = window_start
            run.window_end = window_end
            run.status = "succeeded"
            run.started_at = window_end
            run.completed_at = window_end + timedelta(minutes=12)
            run.blended_spend = spend
            run.blended_impressions = impressions
            run.blended_clicks = clicks
            run.blended_visits = conversions
            run.blended_cpv_target = li.cpv_target
            run.blended_cpv_observed = (
                spend / Decimal(max(1, conversions))
            ).quantize(Decimal("0.0001"))
            run.blended_roas = roas
            run.n_terms_evaluated = n_eval
            run.n_terms_changed = n_changed
            run.n_terms_boosted = n_boosted
            run.n_terms_cut = n_cut
            run.n_terms_zeroed = n_zeroed
            run.digest_text = (
                f"Run sintetico per {li.name}: spese €{spend}, "
                f"{impressions:,} impression, ROAS {roas}. "
                "Generato dallo seed demo — dati non reali."
            )
            run.digest_generated_at = window_end + timedelta(minutes=15)

            # Wipe & rebuild decisions for this run — fully idempotent.
            await db.execute(delete(Decision).where(Decision.run_id == run_id))

            n_dec = rng.randint(15, 30)
            for idx in range(n_dec):
                lever_name, terms = rng.choice(LEVERS)
                targeting_key, value = rng.choice(terms)
                prev_mod = _round_decimal(
                    Decimal(str(rng.uniform(0.80, 1.20))), 3
                )
                new_mod = _round_decimal(
                    Decimal(str(rng.uniform(0.50, 1.50))), 3
                )
                reason = rng.choice(REASONS)
                note = _decision_note(lever_name, reason, value)

                dec = Decision(
                    id=_make_decision_id(run_id, idx),
                    tenant_id=tenant_id,
                    run_id=run_id,
                    targeting_module=lever_name,
                    targeting_key=targeting_key,
                    value=value,
                    field_label=f"{lever_name.title()} / {value}",
                    previous_modifier=prev_mod,
                    new_modifier=new_mod,
                    reason=reason,
                    note=note,
                    observed_impressions=rng.randint(500, 25_000),
                    observed_clicks=rng.randint(2, 250),
                    observed_visits=rng.randint(0, 60),
                    observed_cpv=_round_decimal(
                        Decimal(str(rng.uniform(0.20, 1.10))), 4
                    ),
                    status=rng.choice(["proposed", "approved", "applied"]),
                )
                db.add(dec)
                n_decisions += 1

            # 0-2 violation notes appended as extra synthetic Decisions whose
            # ``note`` carries the ``constraint_violated_*`` prefix that the
            # reporting layer matches.
            n_viol = rng.choice([0, 1, 1, 2])
            for viol_idx in range(n_viol):
                viol_prefix = rng.choice(VIOLATION_PREFIXES)
                lever_name, terms = rng.choice(LEVERS)
                targeting_key, value = rng.choice(terms)
                db.add(
                    Decision(
                        id=_make_decision_id(run_id, 1000 + viol_idx),
                        tenant_id=tenant_id,
                        run_id=run_id,
                        targeting_module=lever_name,
                        targeting_key=targeting_key,
                        value=value,
                        field_label=f"{lever_name.title()} / {value}",
                        previous_modifier=Decimal("1.000"),
                        new_modifier=Decimal("1.000"),
                        reason="smoothed",
                        note=(
                            f"{viol_prefix}: deevAI ha congelato l'adjust per "
                            f"rispettare l'hard constraint."
                        ),
                        status="proposed",
                    )
                )
                n_decisions += 1

            run.n_decisions = n_dec + n_viol
            run.n_changes_proposed = n_dec
            run.n_changes_applied = sum(
                1 for _ in range(n_dec) if rng.random() < 0.55
            )
            n_runs += 1

    await db.flush()
    return n_runs, n_decisions


async def main() -> int:
    rng = random.Random(42)

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionMaker() as db:
        tenant = await _upsert_tenant(db)
        user = await _upsert_user(db, tenant.id)
        await _upsert_setting(db, tenant.id)
        integration = await _upsert_integration(db, tenant.id)
        advertiser = await _upsert_advertiser(db, tenant.id, integration.id)
        line_items = await _upsert_line_items(db, tenant.id, advertiser.id)
        await _upsert_strategy_and_constraints(db, tenant.id)
        n_runs, n_decisions = await _seed_runs_and_decisions(
            db, tenant.id, line_items, rng
        )
        await db.commit()

    await engine.dispose()

    base_url = settings.app_base_url.rstrip("/")
    print("=" * 64)
    print("  deevAI demo tenant ready")
    print("=" * 64)
    print(f"  tenant_id      : {tenant.id}")
    print(f"  tenant_slug    : {tenant.slug}")
    print(f"  user_id        : {user.id}")
    print(f"  login email    : demo@deevai.app")
    print(f"  login password : {DEMO_PASSWORD}")
    print(f"  line items     : {len(line_items)}")
    print(f"  runs seeded    : {n_runs}")
    print(f"  decisions      : {n_decisions}")
    print()
    print(f"  Login URL      : {base_url}/login")
    print(f"  One-click demo : {base_url}/api/v1/auth/demo-login  (POST, no body)")
    print()
    print(f"  Export this to enable demo middleware + endpoint:")
    print(f"      export DEMO_TENANT_ID={tenant.id}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
