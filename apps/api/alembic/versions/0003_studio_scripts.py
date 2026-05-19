"""studio scripts — Custom Bidding scripts, objective weights, simulation runs

Revision ID: 0003_studio_scripts
Revises: 0002_reporting_metrics
Create Date: 2026-05-19

Adds the persistence layer behind the "Studio" surface in the FE — the
3-slider product (Performance / Quality / Reach) that lets a customer
generate a DV360 Custom Bidding scoring script and simulate its score
distribution on a synthetic dataset.

Three additive tables, all tenant-scoped:

  * ``custom_bidding_scripts`` — one row per generated script.
    ``status`` follows: draft → simulated → uploaded → active → archived.

  * ``objective_weights`` — 1:1 with the script (one row per script in v1).
    Stores the slider triplet that *generated* this script; the three
    columns are constrained individually to [0..100] and jointly to sum
    to 100. Splitting it from the script row keeps a clean shape for
    future versioning (script v2 with different weights → new row +
    script_id stays unique).

  * ``simulation_runs`` — every "Simulate" click produces one row, with
    the distribution + counters captured as JSONB so the report shape
    can evolve without a migration.

Naming is provider-agnostic on purpose (no ``amazon_*``/``google_*``
prefixes); Engine B's first consumer is DV360 but the same shape will
ship to other DSPs.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_studio_scripts"
down_revision: Union[str, None] = "0002_reporting_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- custom_bidding_scripts ------------------------------------------------
    op.create_table(
        "custom_bidding_scripts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("line_item_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
            comment="draft | simulated | uploaded | active | archived",
        ),
        sa.Column("script_source", sa.Text(), nullable=False),
        sa.Column("script_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_cbs_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["line_item_id"], ["line_items.id"],
            name="fk_cbs_line_item",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"],
            name="fk_cbs_user",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "name",
            name="uq_cbs_tenant_name",
        ),
    )
    op.create_index(
        op.f("ix_custom_bidding_scripts_tenant_id"),
        "custom_bidding_scripts", ["tenant_id"], unique=False,
    )
    op.create_index(
        op.f("ix_custom_bidding_scripts_line_item_id"),
        "custom_bidding_scripts", ["line_item_id"], unique=False,
    )
    op.create_index(
        op.f("ix_custom_bidding_scripts_status"),
        "custom_bidding_scripts", ["status"], unique=False,
    )

    # --- objective_weights -----------------------------------------------------
    op.create_table(
        "objective_weights",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("script_id", sa.String(length=36), nullable=False),
        sa.Column("performance_pct", sa.Integer(), nullable=False),
        sa.Column("quality_pct", sa.Integer(), nullable=False),
        sa.Column("reach_pct", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["script_id"], ["custom_bidding_scripts.id"],
            name="fk_ow_script",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("script_id", name="uq_ow_script"),
        sa.CheckConstraint(
            "performance_pct >= 0 AND performance_pct <= 100",
            name="ck_ow_performance_range",
        ),
        sa.CheckConstraint(
            "quality_pct >= 0 AND quality_pct <= 100",
            name="ck_ow_quality_range",
        ),
        sa.CheckConstraint(
            "reach_pct >= 0 AND reach_pct <= 100",
            name="ck_ow_reach_range",
        ),
        sa.CheckConstraint(
            "performance_pct + quality_pct + reach_pct = 100",
            name="ck_ow_sum_100",
        ),
    )
    op.create_index(
        op.f("ix_objective_weights_script_id"),
        "objective_weights", ["script_id"], unique=False,
    )

    # --- simulation_runs -------------------------------------------------------
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("script_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column(
            "dataset_kind",
            sa.String(length=32),
            nullable=False,
            comment="synthetic | floodlight_historical",
        ),
        sa.Column("n_impressions", sa.Integer(), nullable=False),
        sa.Column("n_scored", sa.Integer(), nullable=False),
        sa.Column("n_excluded", sa.Integer(), nullable=False),
        sa.Column(
            "distribution_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["script_id"], ["custom_bidding_scripts.id"],
            name="fk_sr_script",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name="fk_sr_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_simulation_runs_script_id"),
        "simulation_runs", ["script_id"], unique=False,
    )
    op.create_index(
        op.f("ix_simulation_runs_tenant_id"),
        "simulation_runs", ["tenant_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_simulation_runs_tenant_id"), table_name="simulation_runs")
    op.drop_index(op.f("ix_simulation_runs_script_id"), table_name="simulation_runs")
    op.drop_table("simulation_runs")

    op.drop_index(op.f("ix_objective_weights_script_id"), table_name="objective_weights")
    op.drop_table("objective_weights")

    op.drop_index(op.f("ix_custom_bidding_scripts_status"), table_name="custom_bidding_scripts")
    op.drop_index(op.f("ix_custom_bidding_scripts_line_item_id"), table_name="custom_bidding_scripts")
    op.drop_index(op.f("ix_custom_bidding_scripts_tenant_id"), table_name="custom_bidding_scripts")
    op.drop_table("custom_bidding_scripts")
