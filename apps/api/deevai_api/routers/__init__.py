"""FastAPI routers — one module per resource."""

from fastapi import APIRouter

from . import (
    actions,
    auth,
    advertisers,
    digests,
    integrations,
    line_items,
    mai,
    meta_agent,
    optimization,
    proposals,
    reporting,
    runs,
    settings,
    setup_agent,
    studio,
    tenants,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(settings.router)
api_router.include_router(actions.router)
api_router.include_router(optimization.strategies_router)
api_router.include_router(optimization.constraints_router)
api_router.include_router(advertisers.router)
api_router.include_router(integrations.router)
api_router.include_router(line_items.router)
api_router.include_router(digests.router)
api_router.include_router(runs.router)
api_router.include_router(meta_agent.line_items_router)
api_router.include_router(meta_agent.proposals_router)
api_router.include_router(setup_agent.router)
api_router.include_router(proposals.router)
api_router.include_router(mai.router)
api_router.include_router(reporting.router)
api_router.include_router(studio.router)

__all__ = ["api_router"]
