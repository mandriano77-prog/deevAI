"""tenant is_demo — flag demo tenants for read-only middleware + UI banner

Revision ID: 0004_tenant_is_demo
Revises: 0002_reporting_metrics
Create Date: 2026-05-19

Adds a boolean ``is_demo`` column on ``tenants`` so the frontend can render
the amber "Stai navigando l'account demo" banner and the API middleware can
short-circuit any state-changing call from a demo session.

Notes
-----
* The column is ``NOT NULL DEFAULT FALSE`` so every existing tenant gets
  the value ``false`` at migration time without an explicit backfill.
* We add a **partial index** scoped to ``WHERE is_demo = TRUE`` — there will
  realistically be 1 demo tenant, so the partial index is essentially free
  and lets ``WHERE is_demo IS TRUE`` lookups (used by reporting / health
  checks) hit an index without bloating the main btree.
* ``down_revision`` is pinned to ``0002_reporting_metrics`` per the demo-mode
  brief. If a sibling revision (e.g. ``0003_studio_scripts``) lands first on
  ``main``, rebase this revision on top of it before merging — just update
  ``down_revision`` to the new head.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_tenant_is_demo"
down_revision: Union[str, None] = "0002_reporting_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``is_demo`` boolean to tenants with a partial index for WHERE is_demo."""
    op.add_column(
        "tenants",
        sa.Column(
            "is_demo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment=(
                "True for the synthetic demo tenant (sales / pitch / self-serve "
                "preview). Read-only at the middleware layer."
            ),
        ),
    )
    # Partial index — only the (1, typically) row(s) with is_demo=true land in it.
    op.create_index(
        "ix_tenants_is_demo_true",
        "tenants",
        ["is_demo"],
        unique=False,
        postgresql_where=sa.text("is_demo = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_tenants_is_demo_true", table_name="tenants")
    op.drop_column("tenants", "is_demo")
