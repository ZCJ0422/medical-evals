from fastapi.testclient import TestClient

from medical_evals_api.main import app


client = TestClient(app)


def test_login_returns_admin_token():
    response = client.post("/api/auth/login", json={"username": "admin", "password": "medical-evals-admin"})
    assert response.status_code == 200
    assert response.json()["user"] == {"username": "admin", "role": "admin"}


def test_invalid_login_is_rejected():
    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_me_requires_authentication():
    assert client.get("/api/me").status_code == 401


def test_me_returns_admin_identity():
    token = client.post("/api/auth/login", json={"username": "admin", "password": "medical-evals-admin"}).json()["access_token"]
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"username": "admin", "role": "admin"}
