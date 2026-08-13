from fastapi.testclient import TestClient

from medical_evals_api.main import app


client = TestClient(app)


def admin_headers():
    token = client.post("/api/auth/login", json={"username": "admin", "password": "medical-evals-admin"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_evaluation_requires_admin():
    response = client.post("/api/evaluations", json={"name": "smoke", "target_model_id": "model", "judge_model_id": "judge", "dataset_version_id": "dataset-v1", "rubric_id": "rubric-v1"})
    assert response.status_code == 401


def test_create_evaluation_returns_queued_task(tmp_path, monkeypatch):
    from medical_evals_api import config
    monkeypatch.setattr(config.settings, "database_path", tmp_path / "tasks.sqlite3")
    response = client.post("/api/evaluations", headers=admin_headers(), json={"name": "smoke", "target_model_id": "model", "judge_model_id": "judge", "dataset_version_id": "dataset-v1", "rubric_id": "rubric-v1"})
    assert response.status_code == 201
    assert response.json()["status"] == "queued"
