#!/usr/bin/env bash
# Render start — migrate then serve (DATABASE_URL is available at runtime).
set -euo pipefail

alembic upgrade head
exec uvicorn deevai_api.main:app --host 0.0.0.0 --port "${PORT}"
