from fastapi.testclient import TestClient

from medical_evals_api.main import app


def test_healthz_returns_ok():
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
