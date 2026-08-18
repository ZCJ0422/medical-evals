from fastapi.testclient import TestClient

from medical_evals_api.auth import create_access_token
from medical_evals_api.config import settings
from medical_evals_api.main import app
from medical_evals_api.repositories.tasks import TaskRepository


def test_lists_created_evaluations(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "tasks.sqlite3")
    TaskRepository(settings.database_path).create(name="visible run", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default")
    client = TestClient(app)

    response = client.get("/api/evaluations", headers={"Authorization": f"Bearer {create_access_token('admin')}"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "visible run"
