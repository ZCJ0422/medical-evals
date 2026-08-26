import pytest
from fastapi.testclient import TestClient

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
    assert snapshot_rows[0]["display_name"] == "Primary"
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
    assert response.json() == {"detail": "Evaluation run not found"}
