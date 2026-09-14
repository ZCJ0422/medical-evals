"""add auditable dataset split catalog

Revision ID: 0003_dataset_catalog
Revises: 0002_evaluation_run_leases
Create Date: 2026-09-09 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_dataset_catalog"
down_revision = "0002_evaluation_run_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_definition_splits",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("evaluation_definition_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("default_sample_limit", sa.Integer(), nullable=False),
        sa.Column("rubric_id", sa.String(length=255), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_definition_id"],
            ["evaluation_definitions.id"],
            name=op.f("fk_evaluation_definition_splits_evaluation_definition_id_evaluation_definitions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("evaluation_definition_id", "id", name=op.f("pk_evaluation_definition_splits")),
        sa.UniqueConstraint("dataset_version_id", name=op.f("uq_evaluation_definition_splits_dataset_version_id")),
        sa.UniqueConstraint(
            "evaluation_definition_id",
            "id",
            name="uq_evaluation_definition_splits_definition_id_id",
        ),
    )
    op.create_index(
        "ix_evaluation_definition_splits_definition_id",
        "evaluation_definition_splits",
        ["evaluation_definition_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_definition_splits_is_enabled",
        "evaluation_definition_splits",
        ["is_enabled"],
        unique=False,
    )

    # Backfill the catalog shipped with the current application. The repository
    # seed path remains idempotent for databases created before this migration.
    split_rows = [
        {
            "id": "dev",
            "evaluation_definition_id": "medqa",
            "dataset_version_id": "medical-medqa.dev.v1",
            "version": "v1",
            "sample_count": 3425,
            "default_sample_limit": 3425,
            "rubric_id": "medical-medqa.default",
            "source_path": "registry/data/medical_medqa/dev.jsonl",
        },
        {
            "id": "smoke",
            "evaluation_definition_id": "healthbench",
            "dataset_version_id": "medical-healthbench.smoke.v1",
            "version": "v1",
            "sample_count": 2,
            "default_sample_limit": 2,
            "rubric_id": "healthbench-default",
            "source_path": "registry/data/medical_healthbench/smoke.jsonl",
        },
        {
            "id": "oss",
            "evaluation_definition_id": "healthbench",
            "dataset_version_id": "medical-healthbench.oss.v1",
            "version": "v1",
            "sample_count": 5000,
            "default_sample_limit": 5000,
            "rubric_id": "healthbench-default",
            "source_path": "dataset/HealthBench/2025-05-07-06-14-12_oss_eval.jsonl",
        },
        {
            "id": "hard",
            "evaluation_definition_id": "healthbench",
            "dataset_version_id": "medical-healthbench.hard.v1",
            "version": "v1",
            "sample_count": 1000,
            "default_sample_limit": 1000,
            "rubric_id": "healthbench-default",
            "source_path": "dataset/HealthBench/hard_2025-05-08-21-00-10.jsonl",
        },
        {
            "id": "consensus",
            "evaluation_definition_id": "healthbench",
            "dataset_version_id": "medical-healthbench.consensus.v1",
            "version": "v1",
            "sample_count": 3671,
            "default_sample_limit": 3671,
            "rubric_id": "healthbench-default",
            "source_path": "dataset/HealthBench/consensus_2025-05-09-20-00-46.jsonl",
        },
    ]
    # Only backfill definitions that already exist. Fresh databases are seeded
    # by the repository; inserting orphan splits breaks PostgreSQL foreign keys.
    splits = sa.table("evaluation_definition_splits", *[sa.column(name) for name in split_rows[0]])
    definitions = sa.table("evaluation_definitions", sa.column("id"))
    for row in split_rows:
        values = sa.select(*[sa.literal(value) for value in row.values()]).where(
            sa.exists(sa.select(definitions.c.id).where(definitions.c.id == row["evaluation_definition_id"]))
        )
        op.execute(splits.insert().from_select(list(row), values))


def downgrade() -> None:
    op.drop_index("ix_evaluation_definition_splits_is_enabled", table_name="evaluation_definition_splits")
    op.drop_index("ix_evaluation_definition_splits_definition_id", table_name="evaluation_definition_splits")
    op.drop_table("evaluation_definition_splits")
