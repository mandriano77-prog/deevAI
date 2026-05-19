"""reporting metrics — denormalized decision counters on Run

Revision ID: 0002_reporting_metrics
Revises: 0001_initial_schema
Create Date: 2026-05-19

Adds denormalized decision-distribution counters to the ``runs`` table
so the reporting layer can render top-line KPIs without scanning all
``decisions`` rows on every request.

These columns are **additive and nullable**: existing runs keep working,
the reporting service falls back to live aggregation from ``decisions``
when a counter is NULL.

We deliberately do **not** add a new ``conversions`` column — that maps
1:1 to the existing ``blended_visits`` field (a "visit" *is* the
conversion event in deevAI v1). When the second engine ships and we
need to disambiguate, we'll rename via a follow-up revision.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_reporting_metrics"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add reporting counters to runs (all nullable, additive only)."""
    op.add_column(
        "runs",
        sa.Column(
            "n_terms_evaluated",
            sa.Integer(),
            nullable=True,
            comment="Total ModifierTerms evaluated by the engine this run.",
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "n_terms_changed",
            sa.Integer(),
            nullable=True,
            comment="Terms whose modifier changed (proposed delta != 0).",
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "n_terms_boosted",
            sa.Integer(),
            nullable=True,
            comment="Terms whose new modifier > previous modifier.",
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "n_terms_cut",
            sa.Integer(),
            nullable=True,
            comment="Terms whose new modifier < previous modifier (and > 0).",
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "n_terms_zeroed",
            sa.Integer(),
            nullable=True,
            comment="Terms whose new modifier is 0.0 (killed).",
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "n_terms_zeroed")
    op.drop_column("runs", "n_terms_cut")
    op.drop_column("runs", "n_terms_boosted")
    op.drop_column("runs", "n_terms_changed")
    op.drop_column("runs", "n_terms_evaluated")
