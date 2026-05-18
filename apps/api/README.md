# apps/api — deevAI backend

FastAPI + SQLAlchemy 2 (async) + Alembic + Postgres.

## Quickstart

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# from monorepo root, start Postgres first:
# docker compose -f ../../infra/docker-compose.yml up -d

alembic upgrade head
uvicorn deevai_api.main:app --reload --port 8000
# → http://localhost:8000/docs
```

## Render deploy

Install `bidagent` from `../../packages/bidagent` (not PyPI). In the Render dashboard set:

**Build Command:**

```bash
chmod +x build.sh start.sh && ./build.sh
```

**Start Command:**

```bash
./start.sh
```

(`start.sh` runs `alembic upgrade head` then uvicorn — migrations need `DATABASE_URL`, which
is only guaranteed at runtime, not during build.)

Do **not** use `pip install -e ".[dev]"` — that fails with `No matching distribution found for bidagent`.

## What's here today (Sprint 1.1)

- `deevai_api/config.py` — pydantic-settings, fails loudly on bad env
- `deevai_api/db.py` — async SQLAlchemy engine + session helpers
- `deevai_api/models/base.py` — `Base`, `TimestampMixin`, `TenantScopedMixin`
- `deevai_api/models/tenant.py` — first model: Tenant root entity
- `deevai_api/main.py` — FastAPI app with `/health` and `/`

## What's coming next

- Sprint 1.2 — full schema: users, integrations (encrypted creds),
  advertisers, line items, runs, decisions, settings. Alembic migrations.
- Sprint 1.3 — Google DV360 OAuth callback + KMS-backed secrets vault
- Sprint 1.4 — onboarding endpoints + tenant-scoping middleware
- Sprint 2 — runs/decisions endpoints (drive the dashboard)
