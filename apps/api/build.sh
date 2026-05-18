#!/usr/bin/env bash
# Render build — install deps only (no DB: DATABASE_URL may be unavailable here).
set -euo pipefail

pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
