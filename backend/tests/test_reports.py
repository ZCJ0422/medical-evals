from fastapi.testclient import TestClient

from medical_evals_api.config import settings
from medical_evals_api.main import app
from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.services.reports import ReportService


def test_html_report_is_written_under_task_artifacts(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="smoke", target_model_id="model", judge_model_id="judge", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    path = ReportService(repo, tmp_path / "artifacts").generate_html(task.task_id)
    assert path.exists()
    assert task.task_id in path.read_text()


def test_report_route_rejects_unregistered_artifact(tmp_path, monkeypatch):
    database_path = tmp_path / "tasks.sqlite3"
    artifact_dir = tmp_path / "artifacts"
    from medical_evals_api import config
    import medical_evals_api.database as database

    monkeypatch.setattr(settings, "database_path", database_path)
    monkeypatch.setattr(config.settings, "database_url", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setattr(settings, "artifact_dir", artifact_dir)
    database._build_engine.cache_clear()
    database._build_session_factory.cache_clear()
    database._build_redis.cache_clear()
    unregistered_report = artifact_dir / "not-a-task" / "report.html"
    unregistered_report.parent.mkdir(parents=True)
    unregistered_report.write_text("should not be served", encoding="utf-8")

    token = TestClient(app).post(
        "/api/auth/login",
        json={"username": "admin", "password": "medical-evals-admin"},
    ).json()["access_token"]
    response = TestClient(app).get(
        "/api/evaluations/not-a-task/report",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
