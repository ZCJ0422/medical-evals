import pytest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
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
        "evaluation_definition_splits",
        "evaluation_runs",
        "run_model_snapshots",
        "evaluation_results",
        "evaluation_sample_results",
    } <= set(metadata.tables)


def test_alembic_upgrades_existing_evaluation_runs_with_non_null_names(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'migration.sqlite3'}"
    backend_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "0001_initial_workbench")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash) "
                "VALUES ('user-1', 'migration-user', 'hash')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO model_profiles "
                "(id, user_id, name, base_url, model_name, api_key_encrypted) "
                "VALUES ('profile-1', 'user-1', 'Target', 'https://example.test/v1', "
                "'target-model', 'encrypted')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluation_definitions "
                "(id, name, kind, dataset_version, default_config_json) "
                "VALUES ('medqa', 'MedQA', 'medical-medqa', 'medical-medqa.dev.v1', '{}')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluation_runs "
                "(id, user_id, evaluation_definition_id, target_model_profile_id, status, split, "
                "config_json, progress_json) VALUES "
                "('run-1', 'user-1', 'medqa', 'profile-1', 'queued', 'dev', '{}', '{}')"
            )
        )

    command.upgrade(alembic_config, "head")

    columns = {column["name"]: column for column in inspect(engine).get_columns("evaluation_runs")}
    with engine.connect() as connection:
        migrated_name = connection.execute(
            text("SELECT name FROM evaluation_runs WHERE id = 'run-1'")
        ).scalar_one()

    assert columns["name"]["nullable"] is False
    assert {"lease_owner", "lease_expires_at"} <= columns.keys()
    assert migrated_name == "Evaluation run-1"


@pytest.mark.parametrize("existing_definition", [False, True])
def test_catalog_migration_respects_foreign_keys(tmp_path, existing_definition):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    database_url = f"sqlite+pysqlite:///{tmp_path / 'catalog-migration.sqlite3'}"
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)

    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    event.listen(Engine, "connect", enable_foreign_keys)
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "0002_evaluation_run_leases")
        if existing_definition:
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO evaluation_definitions "
                    "(id, name, kind, dataset_version, default_config_json) "
                    "VALUES ('medqa', 'MedQA', 'medical-medqa', 'medical-medqa.dev.v1', '{}')"
                ))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            assert connection.execute(text("SELECT COUNT(*) FROM evaluation_definition_splits")).scalar_one() == int(existing_definition)
        command.downgrade(config, "0002_evaluation_run_leases")
        assert "evaluation_definition_splits" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        event.remove(Engine, "connect", enable_foreign_keys)
