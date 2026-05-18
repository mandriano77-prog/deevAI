# DeevAI

> The weekly bid-optimization agent for Google DV360.

DeevAI è un agente SaaS che si aggancia all'account Google DV360 di un cliente,
osserva le performance via DV360 Reporting e ogni settimana propone aggiustamenti
ai bid modifier dei line item — il cliente approva con un click.

## Status

Pre-launch. Repo iniziale, MVP in costruzione.

## Stack

- **Frontend**: Next.js 15 (App Router), Tailwind, Recharts — `apps/web`
- **API**: FastAPI 0.13+, SQLAlchemy 2 async, asyncpg, Alembic — `apps/api`
- **Decision engine**: Python package `bidagent` (deterministic optimizer + LLM digest) — `packages/bidagent`
- **DB**: PostgreSQL 16 (Docker locally, Render in prod)
- **OAuth**: per-tenant Google OAuth user-consent (no shared `google-auth` SDK dependency)

## Quick start

```bash
# 1. DB locale (docker-compose)
docker compose -f infra/docker-compose.yml up -d

# 2. API
cd apps/api
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]" -e ../../packages/bidagent
.venv/bin/alembic upgrade head
.venv/bin/uvicorn deevai_api.main:app --reload --port 8000

# 3. Web
cd apps/web
npm install
npm run dev   # http://localhost:3000
```

## Repo layout

```
apps/
  web/          Next.js frontend
  api/          FastAPI backend + Alembic
packages/
  bidagent/     Python decision engine (DV360 reference impl under providers/dv360)
infra/
  docker-compose.yml      Postgres for local dev
  terraform/              Production infra (Render + Cloudflare)
docs/
  MULTI_PROVIDER_REFACTOR.md   Provider abstraction design notes (historical)
```

## Tests

```bash
# bidagent
cd packages/bidagent && .venv/bin/pytest -q

# API
cd apps/api && .venv/bin/pytest -q

# Web build
cd apps/web && npm run build
```

## Provenance

DeevAI nasce dalla codebase MAiNAUS (Amazon DSP). Tutto il codice
Amazon-specific è stato rimosso. La parte di decision engine e
provider abstraction è stata mantenuta e ripulita.
