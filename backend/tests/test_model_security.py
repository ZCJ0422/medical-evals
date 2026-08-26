import pytest
from fastapi.testclient import TestClient

from medical_evals_api import config
from medical_evals_api.database import get_session, model_profiles
from medical_evals_api.main import app
from medical_evals_api.secrets import decrypt_secret


@pytest.fixture
def client(tmp_path, monkeypatch):
    from medical_evals_api import config
    from medical_evals_api import database

    monkeypatch.setattr(config.settings, "database_url", f"sqlite+pysqlite:///{tmp_path / 'model-security.sqlite3'}")
    database._build_engine.cache_clear()
    database._build_session_factory.cache_clear()
    database._build_redis.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


def test_model_profile_api_key_is_encrypted_at_rest(client):
    token = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery staple"},
    ).json()["access_token"]

    response = client.post(
        "/api/v1/models",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Primary",
            "base_url": "https://example.test/v1",
            "model_name": "gpt-4o-mini",
            "api_key": "sk-test-secret",
        },
    )

    assert response.status_code == 201
    profile_id = response.json()["id"]

    session = next(get_session(config.settings))
    try:
        row = session.execute(
            model_profiles.select().where(model_profiles.c.id == profile_id)
        ).mappings().one()
    finally:
        session.close()

    assert row["api_key_encrypted"] != "sk-test-secret"
    assert decrypt_secret(row["api_key_encrypted"]) == "sk-test-secret"
