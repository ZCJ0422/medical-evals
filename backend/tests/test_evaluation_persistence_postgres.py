import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from medical_evals_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from medical_evals_api import config
    import medical_evals_api.database as database

    monkeypatch.setattr(
        config.settings,
        "database_url",
        f"sqlite+pysqlite:///{tmp_path / 'evaluations.sqlite3'}",
    )
    database._build_engine.cache_clear()
    database._build_session_factory.cache_clear()
    database._build_redis.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


def _issue_token(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "correct horse battery staple"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _model_payload(name: str) -> dict[str, str]:
    return {
        "name": name,
        "base_url": "https://example.test/v1",
        "model_name": f"{name.lower()}-model",
        "api_key": f"sk-{name.lower()}-secret",
    }


def _create_model_profile(client: TestClient, token: str, name: str) -> str:
    response = client.post(
        "/api/v1/models",
        headers=_auth(token),
        json=_model_payload(name),
    )
    assert response.status_code == 201
    return response.json()["id"]


class _RecoveryRaceSession:
    def __init__(self, session, *, run_id: str):
        self._session = session
        self._run_id = run_id
        self._triggered = False
        self.renewed_expires_at = None

    def execute(self, statement, *args, **kwargs):
        from medical_evals_api.database import evaluation_runs

        if (
            not self._triggered
            and getattr(statement, "__visit_name__", "") == "update"
            and getattr(getattr(statement, "table", None), "name", "") == evaluation_runs.name
        ):
            self._triggered = True
            future = datetime.now(timezone.utc) + timedelta(seconds=300)
            self.renewed_expires_at = future
            self._session.execute(
                update(evaluation_runs)
                .where(evaluation_runs.c.id == self._run_id)
                .values(lease_expires_at=future, updated_at=future)
            )
        return self._session.execute(statement, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._session, name)


def test_healthbench_requires_judge_profile(client):
    token = _issue_token(client, "alice")
    target_model_id = _create_model_profile(client, token, "Primary")

    response = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "evaluation_definition_id": "healthbench",
            "target_model_id": target_model_id,
            "split": "smoke",
            "sample_limit": 1,
        },
    )

    assert response.status_code == 422


def test_create_run_snapshots_non_secret_model_metadata_and_lists_only_owned_runs(client):
    token = _issue_token(client, "alice")
    other_token = _issue_token(client, "bob")
    target_model_id = _create_model_profile(client, token, "Primary")

    created = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "name": "MedQA smoke",
            "evaluation_definition_id": "medqa",
            "target_model_id": target_model_id,
            "split": "dev",
            "sample_limit": 2,
            "config": {"temperature": 0.1},
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "queued"
    assert payload["evaluation_definition_id"] == "medqa"
    assert payload["target_model_id"] == "primary-model"
    assert payload["judge_model_id"] == ""
    assert "sk-primary-secret" not in created.text

    owned = client.get("/api/v1/evaluations", headers=_auth(token))
    other = client.get("/api/v1/evaluations", headers=_auth(other_token))

    assert owned.status_code == 200
    assert [item["run_id"] for item in owned.json()] == [payload["run_id"]]
    assert other.status_code == 200
    assert other.json() == []

    from medical_evals_api.database import get_session, run_model_snapshots

    session = next(get_session())
    try:
        snapshot_rows = (
            session.execute(
                run_model_snapshots.select().where(
                    run_model_snapshots.c.run_id == payload["run_id"]
                )
            )
            .mappings()
            .all()
        )
    finally:
        session.close()

    assert len(snapshot_rows) == 1
    assert snapshot_rows[0]["profile_role"] == "target"
    # Public profiles use the provider model name as their display name.
    assert snapshot_rows[0]["display_name"] == "primary-model"
    assert snapshot_rows[0]["base_url"] == "https://example.test/v1"
    assert snapshot_rows[0]["model_name"] == "primary-model"
    assert snapshot_rows[0]["api_key_encrypted"] == ""


def test_cross_user_evaluation_run_access_is_rejected(client):
    alice = _issue_token(client, "alice")
    bob = _issue_token(client, "bob")
    target_model_id = _create_model_profile(client, alice, "Primary")
    created = client.post(
        "/api/v1/evaluations",
        headers=_auth(alice),
        json={
            "evaluation_definition_id": "medqa",
            "target_model_id": target_model_id,
            "split": "dev",
            "sample_limit": 1,
        },
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]

    response = client.get(f"/api/v1/evaluations/{run_id}", headers=_auth(bob))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "evaluation_run_not_found"
    assert response.json()["error"]["message"] == "Evaluation run not found"
    assert response.json()["error"]["request_id"]


def test_legacy_fixed_admin_token_uses_persisted_user_for_v1_resources(client):
    from medical_evals_api.auth import create_access_token
    from medical_evals_api.config import settings
    from medical_evals_api.database import evaluation_runs, get_session, model_profiles, users

    token = create_access_token(settings.fixed_admin_username)
    model_id = _create_model_profile(client, token, "Legacy Admin Target")
    created = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "evaluation_definition_id": "medqa",
            "target_model_id": model_id,
            "split": "dev",
            "sample_limit": 1,
        },
    )

    assert created.status_code == 201
    session = next(get_session())
    try:
        admin_id = session.execute(
            users.select()
            .with_only_columns(users.c.id)
            .where(users.c.username == settings.fixed_admin_username)
        ).scalar_one()
        profile_user_id = session.execute(
            model_profiles.select()
            .with_only_columns(model_profiles.c.user_id)
            .where(model_profiles.c.id == model_id)
        ).scalar_one()
        run_user_id = session.execute(
            evaluation_runs.select()
            .with_only_columns(evaluation_runs.c.user_id)
            .where(evaluation_runs.c.id == created.json()["run_id"])
        ).scalar_one()
    finally:
        session.close()

    assert admin_id != "fixed-admin"
    assert profile_user_id == admin_id
    assert run_user_id == admin_id


def test_sqlalchemy_worker_leases_enforce_ownership_and_recovery(client):
    from medical_evals_api.database import evaluation_runs, get_session
    from medical_evals_api.repositories.evaluations import EvaluationRepository
    from medical_evals_api.schemas.common import TaskProgress, TaskStatus

    token = _issue_token(client, "lease-user")
    target_model_id = _create_model_profile(client, token, "Lease Target")
    created = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "evaluation_definition_id": "medqa",
            "target_model_id": target_model_id,
            "split": "dev",
            "sample_limit": 1,
        },
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]

    session = next(get_session())
    try:
        repository = EvaluationRepository(session)
        claimed = repository.claim_next("worker-a", lease_seconds=60)
        assert claimed is not None
        assert claimed.run_id == run_id
        assert claimed.status == TaskStatus.RUNNING
        assert claimed.lease_owner == "worker-a"
        assert isinstance(claimed.lease_expires_at, datetime)
        assert not repository.renew_lease(run_id, "worker-b", lease_seconds=60)
        assert repository.renew_lease(run_id, "worker-a", lease_seconds=60)
        assert repository.recover_interrupted_tasks("startup recovery") == 0

        session.execute(
            update(evaluation_runs)
            .where(evaluation_runs.c.id == run_id)
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        session.commit()
        assert repository.recover_expired_leases("lease expired") == [run_id]
        recovered = repository.get(run_id)
        assert recovered is not None
        assert recovered.status == TaskStatus.QUEUED
        assert recovered.error is None
        assert recovered.lease_owner == ""
        assert recovered.lease_expires_at is None
        assert run_id in repository.list_queued_run_ids()
        with pytest.raises(RuntimeError, match="Worker lease lost"):
            repository.update_progress(run_id, TaskProgress(stage="late write"), "worker-a")
        with pytest.raises(RuntimeError, match="Worker lease lost"):
            repository.save_result(
                run_id,
                total_score=1.0,
                dimension_scores={},
                error_categories={},
                completed_count=1,
                failed_count=0,
                retry_count=0,
                worker_id="worker-a",
            )
    finally:
        session.close()


def test_recover_expired_leases_skips_rows_renewed_before_conditional_update(client):
    from medical_evals_api.database import evaluation_runs, get_session
    from medical_evals_api.repositories.evaluations import EvaluationRepository
    from medical_evals_api.schemas.common import TaskStatus

    token = _issue_token(client, "lease-race-user")
    target_model_id = _create_model_profile(client, token, "Lease Race Target")
    created = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "evaluation_definition_id": "medqa",
            "target_model_id": target_model_id,
            "split": "dev",
            "sample_limit": 1,
        },
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]

    session = next(get_session())
    try:
        repository = EvaluationRepository(session)
        claimed = repository.claim_next("worker-a", lease_seconds=60)
        assert claimed is not None
        session.execute(
            update(evaluation_runs)
            .where(evaluation_runs.c.id == run_id)
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        session.commit()

        race_session = _RecoveryRaceSession(session, run_id=run_id)
        repository.session = race_session
        recovered_ids = repository.recover_expired_leases("lease expired")

        assert recovered_ids == []
        recovered = repository.get(run_id)
        assert recovered is not None
        assert recovered.status == TaskStatus.RUNNING
        assert recovered.lease_owner == "worker-a"
        assert recovered.lease_expires_at is not None
        assert race_session.renewed_expires_at is not None
        assert recovered.lease_expires_at.isoformat().startswith(
            race_session.renewed_expires_at.replace(tzinfo=None).isoformat(timespec="seconds")
        )
    finally:
        session.close()


def test_repository_cancel_and_delete_are_conditionally_atomic(client):
    from medical_evals_api.database import get_session
    from medical_evals_api.repositories.evaluations import EvaluationRepository
    from medical_evals_api.schemas.common import TaskStatus

    token = _issue_token(client, "atomic-user")
    target_model_id = _create_model_profile(client, token, "Atomic Target")
    completed = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "evaluation_definition_id": "medqa",
            "target_model_id": target_model_id,
            "split": "dev",
            "sample_limit": 1,
        },
    )
    running = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "evaluation_definition_id": "medqa",
            "target_model_id": target_model_id,
            "split": "dev",
            "sample_limit": 1,
        },
    )
    assert completed.status_code == 201
    assert running.status_code == 201

    session = next(get_session())
    try:
        repository = EvaluationRepository(session)
        repository.set_status(completed.json()["run_id"], TaskStatus.COMPLETED)
        repository.set_status(running.json()["run_id"], TaskStatus.RUNNING)

        completed_run, changed = repository.cancel_if_active(completed.json()["run_id"])
        assert changed is False
        assert completed_run is not None
        assert completed_run.status == TaskStatus.COMPLETED

        outcome = repository.delete_if_not_running(running.json()["run_id"])
        assert outcome == "conflict"
        still_running = repository.get(running.json()["run_id"])
        assert still_running is not None
        assert still_running.status == TaskStatus.RUNNING
    finally:
        session.close()


def _alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@pytest.mark.postgres
def test_postgres_migration_and_worker_lease_integration():
    database_url = os.getenv("MEDICAL_EVALS_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip(
            "PostgreSQL integration unavailable: set MEDICAL_EVALS_TEST_POSTGRES_URL "
            "to a disposable PostgreSQL database"
        )

    schema_name = f"medical_evals_test_{uuid4().hex}"
    base_engine = create_engine(database_url)
    scoped_url = make_url(database_url).update_query_dict(
        {"options": f"-csearch_path={schema_name}"}
    )
    scoped_database_url = scoped_url.render_as_string(hide_password=False)
    with base_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')

    scoped_engine = create_engine(scoped_database_url)
    try:
        config = _alembic_config(scoped_database_url)
        command.upgrade(config, "0001_initial_workbench")
        with scoped_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, username, password_hash) "
                    "VALUES ('pg-user', 'pg-user', 'hash')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO model_profiles "
                    "(id, user_id, name, base_url, model_name, api_key_encrypted) "
                    "VALUES ('pg-profile', 'pg-user', 'Target', 'https://example.test/v1', "
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
                    "('pg-run', 'pg-user', 'medqa', 'pg-profile', 'queued', 'dev', '{}', '{}')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO run_model_snapshots "
                    "(id, run_id, profile_role, source_model_profile_id, display_name, base_url, "
                    "model_name, api_key_encrypted) VALUES "
                    "('pg-snapshot', 'pg-run', 'target', 'pg-profile', 'Target', "
                    "'https://example.test/v1', 'target-model', '')"
                )
            )

        command.upgrade(config, "head")
        columns = {
            column["name"]: column
            for column in inspect(scoped_engine).get_columns("evaluation_runs")
        }
        assert columns["name"]["nullable"] is False
        assert {"lease_owner", "lease_expires_at"} <= columns.keys()

        session_factory = sessionmaker(
            bind=scoped_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        from medical_evals_api.database import evaluation_runs
        from medical_evals_api.repositories.evaluations import EvaluationRepository
        from medical_evals_api.schemas.common import TaskStatus

        first_session = session_factory()
        second_session = session_factory()
        try:
            first_repository = EvaluationRepository(first_session)
            second_repository = EvaluationRepository(second_session)
            claimed = first_repository.claim_next("postgres-worker", lease_seconds=60)
            assert claimed is not None
            assert claimed.run_id == "pg-run"
            assert claimed.name == "Evaluation pg-run"
            assert claimed.lease_owner == "postgres-worker"
            assert second_repository.claim_next("other-worker", lease_seconds=60) is None
            assert not second_repository.renew_lease("pg-run", "other-worker", lease_seconds=60)
            assert first_repository.renew_lease("pg-run", "postgres-worker", lease_seconds=60)

            first_session.execute(
                update(evaluation_runs)
                .where(evaluation_runs.c.id == "pg-run")
                .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
            first_session.commit()
            assert second_repository.recover_expired_leases("postgres lease expired") == ["pg-run"]
            recovered = second_repository.get("pg-run")
            assert recovered is not None
            assert recovered.status == TaskStatus.QUEUED
            assert recovered.error is None
            assert "pg-run" in second_repository.list_queued_run_ids()
        finally:
            first_session.close()
            second_session.close()
    finally:
        scoped_engine.dispose()
        with base_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema_name}" CASCADE')
        base_engine.dispose()
