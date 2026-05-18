"""FastAPI app entry point.

For now this is a thin scaffold: health endpoint, CORS, app metadata.
Routers and business logic get added in Sprint 1.2+."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import api_router

settings = get_settings()
logging.basicConfig(level=settings.log_level)
log = logging.getLogger("deevai.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    log.info("DeevAI API starting (env=%s)", settings.app_env)
    yield
    log.info("DeevAI API shutting down")


app = FastAPI(
    title="DeevAI API",
    description="Multi-tenant backend for Google DV360 weekly optimization.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — locked down to known origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_base_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Lightweight liveness check."""
    from .services.secrets_vault import vault_backend

    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "vault": vault_backend(),
    }


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "DeevAI API",
        "version": "0.1.0",
        "docs": "/docs",
    }


# Mount the versioned API routes under /v1
app.include_router(api_router)
