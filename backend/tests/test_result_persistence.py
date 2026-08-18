from fastapi.testclient import TestClient

from medical_evals_api.auth import create_access_token
from medical_evals_api.config import settings
from medical_evals_api.main import app
from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.schemas.common import TaskProgress, TaskStatus
from medical_evals_api.services.results import ResultService


def test_completed_task_exposes_persisted_safe_summary(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="result run", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default")
    repo.save_result(task.task_id, total_score=0.75, dimension_scores={"accuracy": 0.75}, error_categories={"timeout": 1}, completed_count=4, failed_count=1, retry_count=2)

    summary = ResultService(repo).get_public_summary(task.task_id)

    assert summary.total_score == 0.75
    assert summary.dimension_scores == {"accuracy": 0.75}
    assert summary.error_categories == {"timeout": 1}
    assert summary.accuracy == 0.75
    assert summary.parse_success_rate is None


def test_results_endpoint_returns_persisted_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "tasks.sqlite3")
    repo = TaskRepository(settings.database_path)
    task = repo.create(name="api result", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default")
    repo.save_result(task.task_id, total_score=0.5, dimension_scores={"accuracy": 0.5}, error_categories={}, completed_count=2, failed_count=0, retry_count=0)

    response = TestClient(app).get(f"/api/evaluations/{task.task_id}/results", headers={"Authorization": f"Bearer {create_access_token('admin')}"})

    assert response.status_code == 200
    assert response.json()["total_score"] == 0.5
    assert response.json()["accuracy"] == 0.5


def test_results_endpoint_exposes_live_task_context_for_running_evaluation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "tasks.sqlite3")
    repo = TaskRepository(settings.database_path)
    task = repo.create(name="active run", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-healthbench.smoke.v1", rubric_id="healthbench-default")
    repo.update_progress(task.task_id, TaskProgress(completed_count=2, total_count=10, progress_percent=20, success_count=2, stage="judge_model"))
    repo.set_status(task.task_id, TaskStatus.RUNNING, "Judge returned invalid JSON; retrying the sample")

    response = TestClient(app).get(f"/api/evaluations/{task.task_id}/results", headers={"Authorization": f"Bearer {create_access_token('admin')}"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "active run"
    assert payload["status"] == "running"
    assert payload["stage"] == "judge_model"
    assert payload["progress_percent"] == 20
    assert payload["error"] == "Judge returned invalid JSON; retrying the sample"


def test_run_log_endpoint_returns_task_log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "tasks.sqlite3")
    repo = TaskRepository(settings.database_path)
    task = repo.create(name="log run", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default")
    log_path = settings.database_path.parent / "artifacts" / task.task_id / "run.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("task started\nresuming from checkpoint: 1 samples already completed\n", encoding="utf-8")

    response = TestClient(app).get(f"/api/evaluations/{task.task_id}/log", headers={"Authorization": f"Bearer {create_access_token('admin')}"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "task started\nresuming from checkpoint: 1 samples already completed\n"
