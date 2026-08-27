import pytest
from fastapi.testclient import TestClient

from medical_evals_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from medical_evals_api import config
    from medical_evals_api import database

    monkeypatch.setattr(config.settings, "database_url", f"sqlite+pysqlite:///{tmp_path / 'isolation.sqlite3'}")
    database._build_engine.cache_clear()
    database._build_session_factory.cache_clear()
    database._build_redis.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_non_admin_user_cannot_access_admin_only_routes(client):
    issued = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse battery staple"}).json()

    response = client.get("/api/datasets", headers=_auth(issued["access_token"]))

    assert response.status_code == 403
    assert response.json() == {"detail": "Administrator access required"}


def test_me_is_scoped_to_authenticated_user(client):
    alice = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse battery staple"}).json()
    bob = client.post("/api/auth/register", json={"username": "bob", "password": "tr0ub4dor&3"}).json()

    alice_me = client.get("/api/me", headers=_auth(alice["access_token"]))
    bob_me = client.get("/api/me", headers=_auth(bob["access_token"]))

    assert alice_me.status_code == 200
    assert alice_me.json()["username"] == "alice"
    assert bob_me.status_code == 200
    assert bob_me.json()["username"] == "bob"
