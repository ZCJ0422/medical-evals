"""add evaluation run names and worker leases

Revision ID: 0002_evaluation_run_leases
Revises: 0001_initial_workbench
Create Date: 2026-08-26 16:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_evaluation_run_leases"
down_revision = "0001_initial_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluation_runs", sa.Column("name", sa.String(length=255), nullable=True))
    op.add_column("evaluation_runs", sa.Column("lease_owner", sa.String(length=255), nullable=True))
    op.add_column(
        "evaluation_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE evaluation_runs "
            "SET name = 'Evaluation ' || id "
            "WHERE name IS NULL"
        )
    )
    with op.batch_alter_table("evaluation_runs") as batch_op:
        batch_op.alter_column(
            "name",
            existing_type=sa.String(length=255),
            nullable=False,
        )
    op.create_index(
        "ix_evaluation_runs_lease_expires_at",
        "evaluation_runs",
        ["lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_lease_expires_at", table_name="evaluation_runs")
    with op.batch_alter_table("evaluation_runs") as batch_op:
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("lease_owner")
        batch_op.drop_column("name")
