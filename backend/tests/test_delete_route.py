from fastapi.testclient import TestClient

from medical_evals_api.auth import create_access_token
from medical_evals_api.config import settings
from medical_evals_api.main import app
from medical_evals_api.repositories.tasks import TaskRepository


def test_delete_evaluation_allows_cors_and_returns_no_content(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "tasks.sqlite3")
    repo = TaskRepository(settings.database_path)
    task = repo.create(name="delete", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('admin')}", "Origin": "http://127.0.0.1:3000"}

    preflight = client.options(f"/api/evaluations/{task.task_id}", headers={**headers, "Access-Control-Request-Method": "DELETE", "Access-Control-Request-Headers": "authorization,content-type"})
    response = client.delete(f"/api/evaluations/{task.task_id}", headers=headers)

    assert preflight.status_code == 200
    assert response.status_code == 204


def test_delete_evaluation_removes_artifacts_from_database_scoped_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "unrelated-artifacts")
    repo = TaskRepository(settings.database_path)
    task = repo.create(name="delete artifacts", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default")
    artifact_dir = tmp_path / "artifacts" / task.task_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "run.log").write_text("log", encoding="utf-8")

    response = TestClient(app).delete(f"/api/evaluations/{task.task_id}", headers={"Authorization": f"Bearer {create_access_token('admin')}"})

    assert response.status_code == 204
    assert not artifact_dir.exists()
