"""initial workbench schema

Revision ID: 0001_initial_workbench
Revises:
Create Date: 2026-08-26 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_workbench"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="user", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_index("ix_users_status", "users", ["status"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)

    op.create_table(
        "model_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_model_profiles_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_profiles")),
        sa.UniqueConstraint("user_id", "name", name="uq_model_profiles_user_id_name"),
    )
    op.create_index("ix_model_profiles_user_id", "model_profiles", ["user_id"], unique=False)

    op.create_table(
        "evaluation_definitions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("dataset_version", sa.String(length=255), nullable=False),
        sa.Column("requires_judge", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("default_config_json", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_definitions")),
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_definition_id", sa.String(length=64), nullable=False),
        sa.Column("target_model_profile_id", sa.String(length=36), nullable=False),
        sa.Column("judge_model_profile_id", sa.String(length=36), nullable=True),
        sa.Column("retry_of_run_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("split", sa.String(length=64), nullable=False),
        sa.Column("max_samples", sa.Integer(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("progress_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_definition_id"], ["evaluation_definitions.id"], name=op.f("fk_evaluation_runs_evaluation_definition_id_evaluation_definitions")),
        sa.ForeignKeyConstraint(["judge_model_profile_id"], ["model_profiles.id"], name=op.f("fk_evaluation_runs_judge_model_profile_id_model_profiles")),
        sa.ForeignKeyConstraint(["retry_of_run_id"], ["evaluation_runs.id"], name=op.f("fk_evaluation_runs_retry_of_run_id_evaluation_runs")),
        sa.ForeignKeyConstraint(["target_model_profile_id"], ["model_profiles.id"], name=op.f("fk_evaluation_runs_target_model_profile_id_model_profiles")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_evaluation_runs_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_runs")),
    )
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"], unique=False)
    op.create_index("ix_evaluation_runs_user_id", "evaluation_runs", ["user_id"], unique=False)

    op.create_table(
        "run_model_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("profile_role", sa.String(length=32), nullable=False),
        sa.Column("source_model_profile_id", sa.String(length=36), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], name=op.f("fk_run_model_snapshots_run_id_evaluation_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_model_profile_id"], ["model_profiles.id"], name=op.f("fk_run_model_snapshots_source_model_profile_id_model_profiles")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_model_snapshots")),
        sa.UniqueConstraint("run_id", "profile_role", name="uq_run_model_snapshots_run_id_profile_role"),
    )
    op.create_index("ix_run_model_snapshots_run_id", "run_model_snapshots", ["run_id"], unique=False)

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("result_version", sa.String(length=64), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("artifact_index_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], name=op.f("fk_evaluation_results_run_id_evaluation_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_results")),
        sa.UniqueConstraint("run_id", name=op.f("uq_evaluation_results_run_id")),
    )
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"], unique=False)

    op.create_table(
        "evaluation_sample_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_result_id", sa.String(length=36), nullable=True),
        sa.Column("sample_index", sa.Integer(), nullable=False),
        sa.Column("sample_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("judge_json", sa.JSON(), nullable=True),
        sa.Column("artifact_refs_json", sa.JSON(), nullable=False),
        sa.Column("output_artifact_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_result_id"], ["evaluation_results.id"], name=op.f("fk_evaluation_sample_results_evaluation_result_id_evaluation_results"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], name=op.f("fk_evaluation_sample_results_run_id_evaluation_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_sample_results")),
    )
    op.create_index("ix_evaluation_sample_results_run_id", "evaluation_sample_results", ["run_id"], unique=False)
    op.create_index("ix_evaluation_sample_results_run_id_sample_index", "evaluation_sample_results", ["run_id", "sample_index"], unique=True)
    op.create_index("ix_evaluation_sample_results_status", "evaluation_sample_results", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_evaluation_sample_results_status", table_name="evaluation_sample_results")
    op.drop_index("ix_evaluation_sample_results_run_id_sample_index", table_name="evaluation_sample_results")
    op.drop_index("ix_evaluation_sample_results_run_id", table_name="evaluation_sample_results")
    op.drop_table("evaluation_sample_results")
    op.drop_index("ix_evaluation_results_run_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_run_model_snapshots_run_id", table_name="run_model_snapshots")
    op.drop_table("run_model_snapshots")
    op.drop_index("ix_evaluation_runs_user_id", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_definitions")
    op.drop_index("ix_model_profiles_user_id", table_name="model_profiles")
    op.drop_table("model_profiles")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_table("users")
