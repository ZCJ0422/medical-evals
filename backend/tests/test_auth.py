import pytest
from fastapi.testclient import TestClient

from medical_evals_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from medical_evals_api import config
    from medical_evals_api import database

    monkeypatch.setattr(config.settings, "database_url", f"sqlite+pysqlite:///{tmp_path / 'auth.sqlite3'}")
    database._build_engine.cache_clear()
    database._build_session_factory.cache_clear()
    database._build_redis.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


def test_register_returns_tokens_and_user_profile(client):
    response = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse battery staple"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"] == {"username": "alice", "role": "user", "status": "active"}
    assert payload["access_token"]
    assert payload["refresh_token"]


def test_login_returns_user_tokens(client):
    register = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse battery staple"})
    assert register.status_code == 201

    response = client.post("/api/auth/login", json={"username": "alice", "password": "correct horse battery staple"})

    assert response.status_code == 200
    assert response.json()["user"] == {"username": "alice", "role": "user", "status": "active"}


def test_invalid_login_is_rejected_without_disclosing_user_existence(client):
    missing = client.post("/api/auth/login", json={"username": "missing", "password": "wrong-pass"})
    registered = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse battery staple"})
    assert registered.status_code == 201
    wrong_password = client.post("/api/auth/login", json={"username": "alice", "password": "wrong-pass"})

    assert missing.status_code == 401
    assert missing.json() == {"detail": "Invalid credentials"}
    assert wrong_password.status_code == 401
    assert wrong_password.json() == {"detail": "Invalid credentials"}


def test_me_requires_authentication(client):
    assert client.get("/api/me").status_code == 401


def test_me_returns_current_user_identity(client):
    token = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse battery staple"}).json()["access_token"]

    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"username": "alice", "role": "user", "status": "active"}


def test_v1_auth_routes_preserve_primary_contract(client):
    issued = client.post("/api/v1/auth/register", json={"username": "alice", "password": "correct horse battery staple"})

    assert issued.status_code == 201
    payload = issued.json()
    assert payload["user"] == {"username": "alice", "role": "user", "status": "active"}

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {payload['access_token']}"})

    assert me.status_code == 200
    assert me.json() == {"username": "alice", "role": "user", "status": "active"}


def test_refresh_rotates_token_and_revokes_previous_refresh_token(client):
    issued = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse battery staple"}).json()

    refreshed = client.post("/api/auth/refresh", json={"refresh_token": issued["refresh_token"]})

    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != issued["refresh_token"]

    reused = client.post("/api/auth/refresh", json={"refresh_token": issued["refresh_token"]})

    assert reused.status_code == 401
    assert reused.json() == {"detail": "Invalid refresh token"}


def test_logout_revokes_refresh_token(client):
    issued = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse battery staple"}).json()

    response = client.post("/api/auth/logout", json={"refresh_token": issued["refresh_token"]})

    assert response.status_code == 204
    replay = client.post("/api/auth/refresh", json={"refresh_token": issued["refresh_token"]})
    assert replay.status_code == 401


def test_disabled_user_cannot_login_or_access_me(client):
    issued = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse battery staple"}).json()
    from medical_evals_api import config
    from medical_evals_api.database import get_session
    from medical_evals_api.repositories.users import UserRepository

    session = next(get_session(config.settings))
    try:
        repository = UserRepository(session)
        user = repository.get_by_username("alice")
        assert user is not None
        repository.set_status(user.id, "disabled")
    finally:
        session.close()

    login = client.post("/api/auth/login", json={"username": "alice", "password": "correct horse battery staple"})
    me = client.get("/api/me", headers={"Authorization": f"Bearer {issued['access_token']}"})

    assert login.status_code == 401
    assert login.json() == {"detail": "Invalid credentials"}
    assert me.status_code == 403
    assert me.json() == {"detail": "User account is disabled"}
