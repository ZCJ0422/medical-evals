import pytest
from sqlalchemy.orm import Session

from medical_evals_api.config import Settings
from medical_evals_api.database import get_engine, get_redis, get_session, metadata


def test_settings_read_postgres_and_redis_urls(monkeypatch) -> None:
    monkeypatch.setenv("MEDICAL_EVALS_DATABASE_URL", "postgresql+psycopg://u:p@db/medical")
    monkeypatch.setenv("MEDICAL_EVALS_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("MEDICAL_EVALS_JWT_SECRET", "jwt-secret")
    monkeypatch.setenv("MEDICAL_EVALS_ENCRYPTION_SECRET", "enc-secret")

    settings = Settings()

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.redis_url == "redis://redis:6379/0"
    assert settings.jwt_secret == "jwt-secret"
    assert settings.encryption_secret == "enc-secret"


def test_get_session_yields_sqlalchemy_session(monkeypatch) -> None:
    monkeypatch.setenv("MEDICAL_EVALS_DATABASE_URL", "sqlite+pysqlite:///:memory:")

    session = next(get_session())

    try:
        assert isinstance(session, Session)
        assert str(session.bind.url) == "sqlite+pysqlite:///:memory:"
    finally:
        session.close()


def test_get_redis_builds_client_from_settings(monkeypatch) -> None:
    monkeypatch.setenv("MEDICAL_EVALS_REDIS_URL", "redis://redis:6379/5")

    client = get_redis()

    assert client.connection_pool.connection_kwargs["host"] == "redis"
    assert client.connection_pool.connection_kwargs["port"] == 6379
    assert client.connection_pool.connection_kwargs["db"] == 5


def test_metadata_declares_initial_workbench_tables() -> None:
    assert {
        "users",
        "refresh_tokens",
        "model_profiles",
        "evaluation_definitions",
        "evaluation_runs",
        "run_model_snapshots",
        "evaluation_results",
        "evaluation_sample_results",
    } <= set(metadata.tables)
