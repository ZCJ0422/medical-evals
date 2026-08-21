from fastapi.testclient import TestClient

from medical_evals_api.main import app
from medical_evals_api.schemas.common import TaskStatus


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
    response = client.post("/api/evaluations", headers=admin_headers(), json={"name": "smoke", "target_model_id": "model", "judge_model_id": "judge", "dataset_version_id": "medical-medqa.dev.v1", "rubric_id": "medical-medqa.default", "target_base_url": "https://target.example/v1", "judge_base_url": "https://judge.example/v1", "target_api_key": "target-secret", "judge_api_key": "judge-secret"})
    assert response.status_code == 201
    assert response.json()["status"] == "queued"


def test_create_medqa_without_judge_and_name_uses_generated_name(tmp_path, monkeypatch):
    from medical_evals_api import config
    monkeypatch.setattr(config.settings, "database_path", tmp_path / "tasks.sqlite3")
    response = client.post("/api/evaluations", headers=admin_headers(), json={
        "name": "",
        "target_model_id": "model",
        "dataset_version_id": "medical-medqa.dev.v1",
        "rubric_id": "medical-medqa.default",
        "target_base_url": "https://api.example.com/v1",
        "target_api_key": "target-secret",
    })
    assert response.status_code == 201
    assert response.json()["name"].startswith("MedQA-model-")
    assert response.json()["judge_model_id"] == ""
    timestamp = response.json()["name"].rsplit("-", 2)[-2:]
    assert len(timestamp[0]) == 8
    assert len(timestamp[1]) == 6


def test_healthbench_requires_judge_configuration(tmp_path, monkeypatch):
    from medical_evals_api import config
    monkeypatch.setattr(config.settings, "database_path", tmp_path / "tasks.sqlite3")
    response = client.post("/api/evaluations/preflight", headers=admin_headers(), json={
        "name": "healthbench",
        "target_model_id": "model",
        "dataset_version_id": "medical-healthbench.smoke.v1",
        "rubric_id": "medical-healthbench.default",
        "target_base_url": "https://api.example.com/v1",
        "target_api_key": "target-secret",
    })
    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert any("Judge" in error for error in response.json()["errors"])


def test_create_direct_api_key_is_encrypted_and_not_returned(tmp_path, monkeypatch):
    from medical_evals_api import config
    monkeypatch.setattr(config.settings, "database_path", tmp_path / "tasks.sqlite3")
    response = client.post("/api/evaluations", headers=admin_headers(), json={
        "name": "direct-key",
        "target_model_id": "model",
        "dataset_version_id": "medical-medqa.dev.v1",
        "rubric_id": "medical-medqa.default",
        "target_base_url": "https://api.example.com/v1",
        "target_api_key": "target-secret",
    })
    assert response.status_code == 201
    assert "target-secret" not in response.text
    task_id = response.json()["task_id"]
    row = client.get(f"/api/evaluations/{task_id}", headers=admin_headers())
    assert "target-secret" not in row.text


def test_retry_completed_evaluation_creates_new_queued_task(tmp_path, monkeypatch):
    from medical_evals_api import config
    monkeypatch.setattr(config.settings, "database_path", tmp_path / "tasks.sqlite3")
    response = client.post("/api/evaluations", headers=admin_headers(), json={
        "name": "original",
        "target_model_id": "model",
        "dataset_version_id": "medical-medqa.dev.v1",
        "rubric_id": "medical-medqa.default",
        "target_base_url": "https://api.example.com/v1",
        "target_api_key": "target-secret",
    })
    original = response.json()
    repo = __import__("medical_evals_api.repositories.tasks", fromlist=["TaskRepository"]).TaskRepository(config.settings.database_path)
    repo.set_status(original["task_id"], __import__("medical_evals_api.schemas.common", fromlist=["TaskStatus"]).TaskStatus.COMPLETED)

    retried = client.post(f"/api/evaluations/{original['task_id']}/retry", headers=admin_headers())

    assert retried.status_code == 201
    assert retried.json()["status"] == "queued"
    assert retried.json()["task_id"] != original["task_id"]
    assert retried.json()["name"] == "original - retry1"

    repo.set_status(retried.json()["task_id"], TaskStatus.COMPLETED)
    retried_again = client.post(f"/api/evaluations/{retried.json()['task_id']}/retry", headers=admin_headers())

    assert retried_again.status_code == 201
    assert retried_again.json()["name"] == "original - retry2"


def test_resume_partial_evaluation_reuses_same_task(tmp_path, monkeypatch):
    from medical_evals_api import config
    monkeypatch.setattr(config.settings, "database_path", tmp_path / "tasks.sqlite3")
    response = client.post("/api/evaluations", headers=admin_headers(), json={
        "name": "checkpointed",
        "target_model_id": "model",
        "dataset_version_id": "medical-medqa.dev.v1",
        "rubric_id": "medical-medqa.default",
        "target_base_url": "https://api.example.com/v1",
        "target_api_key": "target-secret",
    })
    task_id = response.json()["task_id"]
    repo = __import__("medical_evals_api.repositories.tasks", fromlist=["TaskRepository"]).TaskRepository(config.settings.database_path)
    repo.set_status(task_id, TaskStatus.PARTIAL_FAILED, "one sample failed")

    resumed = client.post(f"/api/evaluations/{task_id}/resume", headers=admin_headers())

    assert resumed.status_code == 200
    assert resumed.json()["task_id"] == task_id
    assert resumed.json()["status"] == "queued"


def test_cancel_running_evaluation_updates_status(tmp_path, monkeypatch):
    from medical_evals_api import config
    monkeypatch.setattr(config.settings, "database_path", tmp_path / "tasks.sqlite3")
    response = client.post("/api/evaluations", headers=admin_headers(), json={
        "name": "running",
        "target_model_id": "model",
        "dataset_version_id": "medical-medqa.dev.v1",
        "rubric_id": "medical-medqa.default",
        "target_base_url": "https://api.example.com/v1",
        "target_api_key": "target-secret",
    })
    task_id = response.json()["task_id"]
    repo = __import__("medical_evals_api.repositories.tasks", fromlist=["TaskRepository"]).TaskRepository(config.settings.database_path)
    repo.set_status(task_id, __import__("medical_evals_api.schemas.common", fromlist=["TaskStatus"]).TaskStatus.RUNNING)

    cancelled = client.post(f"/api/evaluations/{task_id}/cancel", headers=admin_headers())

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_preflight_rejects_api_key_entered_as_base_url(tmp_path, monkeypatch):
    from medical_evals_api import config
    monkeypatch.setattr(config.settings, "database_path", tmp_path / "tasks.sqlite3")
    response = client.post("/api/evaluations/preflight", headers=admin_headers(), json={
        "name": "bad-url",
        "target_model_id": "model",
        "dataset_version_id": "medical-medqa.dev.v1",
        "rubric_id": "medical-medqa.default",
        "target_base_url": "sk-not-a-url",
        "target_api_key": "target-secret",
    })
    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert any("Base URL" in error for error in response.json()["errors"])


def test_preflight_rejects_unknown_dataset_and_mismatched_rubric(tmp_path, monkeypatch):
    from medical_evals_api import config
    monkeypatch.setattr(config.settings, "database_path", tmp_path / "tasks.sqlite3")
    response = client.post("/api/evaluations/preflight", headers=admin_headers(), json={
        "name": "bad-catalog-entry",
        "target_model_id": "model",
        "dataset_version_id": "medical-healthbench.unknown.v1",
        "rubric_id": "medical-healthbench.unknown",
        "target_base_url": "https://api.example.com/v1",
        "target_api_key": "target-secret",
    })
    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert "Unsupported dataset version" in response.json()["errors"]

    mismatched = client.post("/api/evaluations/preflight", headers=admin_headers(), json={
        "name": "bad-rubric",
        "target_model_id": "model",
        "dataset_version_id": "medical-healthbench.smoke.v1",
        "rubric_id": "medical-medqa.default",
        "target_base_url": "https://api.example.com/v1",
        "target_api_key": "target-secret",
        "judge_model_id": "judge",
        "judge_base_url": "https://judge.example.com/v1",
        "judge_api_key": "judge-secret",
    })
    assert mismatched.status_code == 200
    assert any("Rubric must be healthbench-default" in error for error in mismatched.json()["errors"])
