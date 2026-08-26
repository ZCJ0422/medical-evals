from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
import redis
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, MetaData, Numeric, String, Table, Text, UniqueConstraint, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import Settings, settings


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

users = Table(
    "users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(255), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(32), nullable=False, server_default="user"),
    Column("status", String(32), nullable=False, server_default="active"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_users_status", "status"),
)

refresh_tokens = Table(
    "refresh_tokens",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("token_hash", String(255), nullable=False, unique=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_refresh_tokens_user_id", "user_id"),
)

model_profiles = Table(
    "model_profiles",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(255), nullable=False),
    Column("base_url", Text, nullable=False),
    Column("model_name", String(255), nullable=False),
    Column("api_key_encrypted", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "name", name="uq_model_profiles_user_id_name"),
    Index("ix_model_profiles_user_id", "user_id"),
)

evaluation_definitions = Table(
    "evaluation_definitions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("kind", String(64), nullable=False),
    Column("dataset_version", String(255), nullable=False),
    Column("requires_judge", Boolean, nullable=False, server_default="false"),
    Column("default_config_json", JSON, nullable=False),
    Column("is_enabled", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

evaluation_runs = Table(
    "evaluation_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("evaluation_definition_id", String(64), ForeignKey("evaluation_definitions.id"), nullable=False),
    Column("target_model_profile_id", String(36), ForeignKey("model_profiles.id"), nullable=False),
    Column("judge_model_profile_id", String(36), ForeignKey("model_profiles.id")),
    Column("retry_of_run_id", String(36), ForeignKey("evaluation_runs.id")),
    Column("status", String(32), nullable=False),
    Column("split", String(64), nullable=False),
    Column("max_samples", Integer),
    Column("config_json", JSON, nullable=False),
    Column("progress_json", JSON, nullable=False),
    Column("error", Text),
    Column("queued_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_evaluation_runs_user_id", "user_id"),
    Index("ix_evaluation_runs_status", "status"),
)

run_model_snapshots = Table(
    "run_model_snapshots",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("run_id", String(36), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False),
    Column("profile_role", String(32), nullable=False),
    Column("source_model_profile_id", String(36), ForeignKey("model_profiles.id")),
    Column("display_name", String(255), nullable=False),
    Column("base_url", Text, nullable=False),
    Column("model_name", String(255), nullable=False),
    Column("api_key_encrypted", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("run_id", "profile_role", name="uq_run_model_snapshots_run_id_profile_role"),
    Index("ix_run_model_snapshots_run_id", "run_id"),
)

evaluation_results = Table(
    "evaluation_results",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("run_id", String(36), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("result_version", String(64), nullable=False),
    Column("summary_json", JSON, nullable=False),
    Column("artifact_index_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_evaluation_results_run_id", "run_id"),
)

evaluation_sample_results = Table(
    "evaluation_sample_results",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("run_id", String(36), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False),
    Column("evaluation_result_id", String(36), ForeignKey("evaluation_results.id", ondelete="CASCADE")),
    Column("sample_index", Integer, nullable=False),
    Column("sample_id", String(255)),
    Column("status", String(32), nullable=False),
    Column("score", Numeric(10, 4)),
    Column("judge_json", JSON),
    Column("artifact_refs_json", JSON, nullable=False),
    Column("output_artifact_path", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_evaluation_sample_results_run_id", "run_id"),
    Index("ix_evaluation_sample_results_status", "status"),
    Index("ix_evaluation_sample_results_run_id_sample_index", "run_id", "sample_index", unique=True),
)


@lru_cache(maxsize=8)
def _build_engine(database_url: str) -> Engine:
    options = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            options["poolclass"] = StaticPool
    else:
        options["pool_size"] = 5
        options["max_overflow"] = 5
        options["pool_recycle"] = 1800
    return create_engine(database_url, **options)


@lru_cache(maxsize=8)
def _build_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=_build_engine(database_url), autoflush=False, autocommit=False, expire_on_commit=False)


@lru_cache(maxsize=8)
def _build_redis(redis_url: str) -> redis.Redis:
    return redis.Redis.from_url(redis_url)


def get_engine(runtime_settings: Settings | None = None) -> Engine:
    return _build_engine((runtime_settings or Settings()).database_url)


def get_runtime_settings() -> Settings:
    return settings


def get_session(runtime_settings: Settings = Depends(get_runtime_settings)) -> Iterator[Session]:
    session = _build_session_factory(runtime_settings.database_url)()
    try:
        yield session
    finally:
        session.close()


def get_redis(runtime_settings: Settings | None = None) -> redis.Redis:
    return _build_redis((runtime_settings or Settings()).redis_url)
