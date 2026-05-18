"""SQLAlchemy ORM models for deevAI.

Import everything from this module so Alembic's `target_metadata` picks
up the full schema (see `alembic/env.py`)."""

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid, utcnow
from .action import Action
from .advertiser import Advertiser
from .audit_log import AuditLog
from .decision import Decision
from .hard_constraint import HardConstraint
from .integration import Integration
from .agent_proposal import AgentProposal
from .optimization_strategy import OptimizationStrategy
from .line_item import LineItem
from .mai_log import MaiLog
from .run import Run
from .setting import Setting
from .tenant import Tenant
from .user import User

__all__ = [
    "Base",
    "TenantScopedMixin",
    "TimestampMixin",
    "new_uuid",
    "utcnow",
    # domain models
    "Action",
    "Advertiser",
    "AuditLog",
    "Decision",
    "HardConstraint",
    "Integration",
    "AgentProposal",
    "OptimizationStrategy",
    "LineItem",
    "MaiLog",
    "Run",
    "Setting",
    "Tenant",
    "User",
]
