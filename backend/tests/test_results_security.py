import pytest
from fastapi.testclient import TestClient

from medical_evals_api.auth import create_access_token
from medical_evals_api.config import settings
from medical_evals_api.artifacts import ArtifactWriter
from medical_evals_api.main import app
from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.services.results import ResultService
from medical_evals_api.schemas.common import TaskProgress, TaskStatus


@pytest.fixture
def client(tmp_path, monkeypatch):
    from medical_evals_api import config
    import medical_evals_api.database as database

    monkeypatch.setattr(
        config.settings,
        "database_url",
        f"sqlite+pysqlite:///{tmp_path / 'task6-results.sqlite3'}",
    )
    monkeypatch.setattr(config.settings, "artifact_dir", tmp_path / "artifacts")
    database._build_engine.cache_clear()
    database._build_session_factory.cache_clear()
    database._build_redis.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


def _issue_token(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "correct horse battery staple"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(settings.fixed_admin_username)}"}


def _create_model_profile(client: TestClient, token: str, name: str) -> str:
    response = client.post(
        "/api/v1/models",
        headers=_auth(token),
        json={
            "name": name,
            "base_url": "https://example.test/v1",
            "model_name": f"{name.lower()}-model",
            "api_key": f"sk-{name.lower()}-secret",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_run(client: TestClient, token: str, target_model_id: str) -> str:
    response = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "name": "Protected run",
            "evaluation_definition_id": "medqa",
            "target_model_id": target_model_id,
            "split": "dev",
            "sample_limit": 3,
            "config": {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


def _finalize_run(run_id: str, artifact_dir) -> None:
    from medical_evals_api.database import get_session
    from medical_evals_api.repositories.evaluations import EvaluationRepository

    session = next(get_session())
    try:
        repo = EvaluationRepository(session, artifact_dir)
        repo.update_progress(
            run_id,
            TaskProgress(
                completed_count=3,
                total_count=3,
                progress_percent=100,
                success_count=3,
                failed_count=0,
                retry_count=1,
                stage="completed",
            ),
        )
        repo.save_result(
            run_id,
            total_score=0.75,
            dimension_scores={"accuracy": 0.75},
            error_categories={"timeout": 1},
            completed_count=3,
            failed_count=0,
            retry_count=1,
            accuracy=0.75,
            parse_success_rate=1.0,
            request_success_count=3,
            parse_failed_count=0,
        )
        for index in range(3):
            repo.upsert_sample_result(
                run_id,
                {
                    "index": index,
                    "sample_id": f"sample-{index}",
                    "question": f"Question {index}",
                    "raw_output": f"raw answer {index}",
                    "judge": {"verdict": "pass"},
                },
            )
        repo.set_status(run_id, TaskStatus.COMPLETED)
    finally:
        session.close()

    writer = ArtifactWriter(artifact_dir, run_id)
    writer.write_summary({"task_id": run_id, "accuracy": 0.75})
    writer.write_metadata({"run_id": run_id, "entrypoint": "workbench"})
    writer.log("run completed")
    for index in range(3):
        writer.upsert_sample(
            {
                "index": index,
                "sample_id": f"sample-{index}",
                "question": f"Question {index}",
                "raw_output": f"raw answer {index}",
                "judge": {"verdict": "pass"},
            }
        )
    report_path = artifact_dir / run_id / "report.html"
    report_path.write_text("<html><body>report</body></html>", encoding="utf-8")


def _finalize_run_with_artifact_only_samples(run_id: str, artifact_dir) -> None:
    from medical_evals_api.database import get_session
    from medical_evals_api.repositories.evaluations import EvaluationRepository

    session = next(get_session())
    try:
        repo = EvaluationRepository(session, artifact_dir)
        repo.update_progress(
            run_id,
            TaskProgress(
                completed_count=3,
                total_count=3,
                progress_percent=100,
                success_count=3,
                failed_count=0,
                retry_count=1,
                stage="completed",
            ),
        )
        repo.save_result(
            run_id,
            total_score=0.75,
            dimension_scores={"accuracy": 0.75},
            error_categories={"timeout": 1},
            completed_count=3,
            failed_count=0,
            retry_count=1,
            accuracy=0.75,
            parse_success_rate=1.0,
            request_success_count=3,
            parse_failed_count=0,
        )
        repo.set_status(run_id, TaskStatus.COMPLETED)
    finally:
        session.close()

    writer = ArtifactWriter(artifact_dir, run_id)
    for index in range(3):
        writer.upsert_sample(
            {
                "index": index,
                "sample_id": f"artifact-sample-{index}",
                "question": f"Artifact Question {index}",
                "raw_output": f"artifact raw answer {index}",
                "judge": {"verdict": "pass"},
            }
        )


def test_public_summary_contains_aggregates_only(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="smoke",
        target_model_id="model",
        judge_model_id="judge",
        dataset_version_id="dataset-v1",
        rubric_id="rubric-v1",
    )
    summary = ResultService(repo).get_public_summary(task.task_id)
    assert not hasattr(summary, "question")
    assert not hasattr(summary, "standard_answer")


def test_v1_summary_samples_and_artifacts_are_owner_scoped_and_paginated(client, tmp_path):
    alice = _issue_token(client, "alice")
    bob = _issue_token(client, "bob")
    model_id = _create_model_profile(client, alice, "primary")
    run_id = _create_run(client, alice, model_id)
    artifact_dir = tmp_path / "artifacts"
    _finalize_run(run_id, artifact_dir)

    summary = client.get(f"/api/v1/evaluations/{run_id}/summary", headers=_auth(alice))
    assert summary.status_code == 200
    assert summary.json()["status"] == "succeeded"
    assert summary.json()["total_score"] == 0.75
    assert summary.json()["progress"]["completed_count"] == 3

    samples = client.get(
        f"/api/v1/evaluations/{run_id}/samples",
        headers=_auth(alice),
        params={"offset": 1, "limit": 1},
    )
    assert samples.status_code == 200
    assert samples.json()["total"] == 3
    assert samples.json()["has_more"] is True
    assert samples.json()["samples"][0]["sample_id"] == "sample-1"
    assert samples.json()["samples"][0]["raw_output"] == "raw answer 1"

    artifacts = client.get(f"/api/v1/evaluations/{run_id}/artifacts", headers=_auth(alice))
    assert artifacts.status_code == 200
    names = {item["name"] for item in artifacts.json()["artifacts"]}
    assert {"run.log", "summary.json", "metadata.json", "samples.jsonl", "report.html"} <= names

    download = client.get(
        f"/api/v1/evaluations/{run_id}/artifacts/run.log",
        headers=_auth(alice),
    )
    assert download.status_code == 200
    assert "run completed" in download.text

    for path in (
        f"/api/v1/evaluations/{run_id}",
        f"/api/v1/evaluations/{run_id}/summary",
        f"/api/v1/evaluations/{run_id}/samples",
        f"/api/v1/evaluations/{run_id}/artifacts",
        f"/api/v1/evaluations/{run_id}/artifacts/run.log",
    ):
        response = client.get(path, headers=_auth(bob))
        assert response.status_code == 404
        assert response.json()["error"]["code"] in {"evaluation_run_not_found", "artifact_not_found"}
        assert response.json()["error"]["request_id"]

    admin_summary = client.get(
        f"/api/v1/evaluations/{run_id}/summary",
        headers=_admin_auth(),
    )
    assert admin_summary.status_code == 200
    assert admin_summary.json()["run_id"] == run_id


def test_v1_sample_pagination_validation_uses_error_envelope(client):
    token = _issue_token(client, "alice")
    model_id = _create_model_profile(client, token, "primary")
    run_id = _create_run(client, token, model_id)

    response = client.get(
        f"/api/v1/evaluations/{run_id}/samples",
        headers=_auth(token),
        params={"offset": -1, "limit": 1},
    )

    assert response.status_code == 422
    payload = response.json()["error"]
    assert payload["code"] == "invalid_request"
    assert payload["message"] == "Invalid pagination"
    assert payload["request_id"]


def test_v1_samples_fall_back_to_artifact_jsonl_when_db_rows_are_absent(client, tmp_path):
    token = _issue_token(client, "alice")
    model_id = _create_model_profile(client, token, "primary")
    run_id = _create_run(client, token, model_id)
    artifact_dir = tmp_path / "artifacts"
    _finalize_run_with_artifact_only_samples(run_id, artifact_dir)

    response = client.get(
        f"/api/v1/evaluations/{run_id}/samples",
        headers=_auth(token),
        params={"offset": 1, "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["offset"] == 1
    assert payload["limit"] == 1
    assert payload["has_more"] is True
    assert payload["samples"] == [
        {
            "index": 1,
            "sample_id": "artifact-sample-1",
            "question": "Artifact Question 1",
            "raw_output": "artifact raw answer 1",
            "judge": {"verdict": "pass"},
        }
    ]
