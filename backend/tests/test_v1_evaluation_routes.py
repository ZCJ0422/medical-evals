from datetime import timedelta, timezone

import redis
import pytest
from fastapi.testclient import TestClient

from medical_evals_api.auth import create_access_token
from medical_evals_api.config import settings
from medical_evals_api.main import app
from medical_evals_api.schemas.common import TaskStatus


@pytest.fixture
def client(tmp_path, monkeypatch):
    from medical_evals_api import config
    import medical_evals_api.database as database

    monkeypatch.setattr(
        config.settings,
        "database_url",
        f"sqlite+pysqlite:///{tmp_path / 'task6-routes.sqlite3'}",
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


def _create_run(client: TestClient, token: str, target_model_id: str, **overrides) -> dict:
    payload = {
        "name": "Task 6 MedQA",
        "evaluation_definition_id": "medqa",
        "target_model_id": target_model_id,
        "split": "dev",
        "sample_limit": 2,
        "config": {},
    }
    payload.update(overrides)
    response = client.post("/api/v1/evaluations", headers=_auth(token), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _set_status(run_id: str, task_status: TaskStatus) -> None:
    from medical_evals_api.database import get_session
    from medical_evals_api.repositories.evaluations import EvaluationRepository

    session = next(get_session())
    try:
        EvaluationRepository(session).set_status(run_id, task_status)
    finally:
        session.close()


def test_v1_create_returns_201_immediately_and_run_remains_visible_on_enqueue_failure(client, monkeypatch):
    token = _issue_token(client, "alice")
    model_id = _create_model_profile(client, token, "primary")

    def broken_enqueue(self, run_id: str) -> None:
        raise redis.exceptions.ConnectionError(f"redis down for {run_id}")

    monkeypatch.setattr(
        "medical_evals_api.redis_queue.RedisTaskQueue.enqueue",
        broken_enqueue,
    )

    response = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "name": "Immediate create",
            "evaluation_definition_id": "medqa",
            "target_model_id": model_id,
            "split": "dev",
            "sample_limit": 1,
            "config": {"temperature": 0.1},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run_id"]
    assert payload["status"] == "queued"
    assert response.headers["x-request-id"]

    detail = client.get(
        f"/api/v1/evaluations/{payload['run_id']}",
        headers=_auth(token),
    )
    assert detail.status_code == 200
    assert detail.json()["run_id"] == payload["run_id"]
    assert detail.json()["status"] == "queued"


def test_v1_list_and_detail_enforce_owner_scope_and_support_status_filter(client):
    alice = _issue_token(client, "alice")
    bob = _issue_token(client, "bob")
    target_model_id = _create_model_profile(client, alice, "primary")

    queued = _create_run(client, alice, target_model_id, name="Queued run")
    succeeded = _create_run(client, alice, target_model_id, name="Succeeded run")
    failed = _create_run(client, alice, target_model_id, name="Failed run")
    _set_status(succeeded["run_id"], TaskStatus.COMPLETED)
    _set_status(failed["run_id"], TaskStatus.FAILED)

    filtered = client.get(
        "/api/v1/evaluations",
        headers=_auth(alice),
        params={"status": "succeeded"},
    )
    assert filtered.status_code == 200
    assert [item["run_id"] for item in filtered.json()] == [succeeded["run_id"]]

    paginated = client.get(
        "/api/v1/evaluations",
        headers=_auth(alice),
        params={"limit": 2, "offset": 1},
    )
    assert paginated.status_code == 200
    assert len(paginated.json()) == 2

    forbidden = client.get(
        f"/api/v1/evaluations/{queued['run_id']}",
        headers=_auth(bob),
    )
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "evaluation_run_not_found"
    assert forbidden.json()["error"]["message"] == "Evaluation run not found"
    assert forbidden.json()["error"]["request_id"]


def test_v1_invalid_state_transitions_return_409_with_error_envelope(client):
    token = _issue_token(client, "alice")
    target_model_id = _create_model_profile(client, token, "primary")

    queued = _create_run(client, token, target_model_id, name="Queued run")
    retry_queued = client.post(
        f"/api/v1/evaluations/{queued['run_id']}/retry",
        headers=_auth(token),
    )
    assert retry_queued.status_code == 409
    assert retry_queued.json()["error"]["code"] == "invalid_state_transition"

    completed = _create_run(client, token, target_model_id, name="Completed run")
    _set_status(completed["run_id"], TaskStatus.COMPLETED)
    cancel_completed = client.post(
        f"/api/v1/evaluations/{completed['run_id']}/cancel",
        headers=_auth(token),
    )
    assert cancel_completed.status_code == 409
    assert cancel_completed.json()["error"]["message"] == "Only queued or running evaluations can be cancelled"

    running = _create_run(client, token, target_model_id, name="Running run")
    _set_status(running["run_id"], TaskStatus.RUNNING)
    delete_running = client.delete(
        f"/api/v1/evaluations/{running['run_id']}",
        headers=_auth(token),
    )
    assert delete_running.status_code == 409
    assert delete_running.json()["error"]["code"] == "invalid_state_transition"


def test_v1_cancel_retry_and_delete_success_paths(client):
    token = _issue_token(client, "alice")
    target_model_id = _create_model_profile(client, token, "primary")

    queued = _create_run(client, token, target_model_id, name="Queued run")
    cancel = client.post(
        f"/api/v1/evaluations/{queued['run_id']}/cancel",
        headers=_auth(token),
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    retry = client.post(
        f"/api/v1/evaluations/{queued['run_id']}/retry",
        headers=_auth(token),
    )
    assert retry.status_code == 201
    assert retry.json()["retry_of_run_id"] == queued["run_id"]
    assert retry.json()["status"] == "queued"

    completed = _create_run(client, token, target_model_id, name="Delete me")
    _set_status(completed["run_id"], TaskStatus.COMPLETED)
    deleted = client.delete(
        f"/api/v1/evaluations/{completed['run_id']}",
        headers=_auth(token),
    )
    assert deleted.status_code == 204

    missing = client.get(
        f"/api/v1/evaluations/{completed['run_id']}",
        headers=_auth(token),
    )
    assert missing.status_code == 404


def test_v1_cross_user_mutations_are_hidden(client):
    alice = _issue_token(client, "alice")
    bob = _issue_token(client, "bob")
    target_model_id = _create_model_profile(client, alice, "primary")
    run = _create_run(client, alice, target_model_id, name="Protected run")
    _set_status(run["run_id"], TaskStatus.COMPLETED)

    for method, path in (
        ("post", f"/api/v1/evaluations/{run['run_id']}/cancel"),
        ("post", f"/api/v1/evaluations/{run['run_id']}/retry"),
        ("delete", f"/api/v1/evaluations/{run['run_id']}"),
    ):
        response = getattr(client, method)(path, headers=_auth(bob))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "evaluation_run_not_found"


def test_v1_admin_can_list_and_read_other_users_runs(client):
    alice = _issue_token(client, "alice")
    target_model_id = _create_model_profile(client, alice, "primary")
    run = _create_run(client, alice, target_model_id, name="Alice run")

    listed = client.get("/api/v1/evaluations", headers=_admin_auth())
    assert listed.status_code == 200
    assert [item["run_id"] for item in listed.json()] == [run["run_id"]]

    detail = client.get(
        f"/api/v1/evaluations/{run['run_id']}",
        headers=_admin_auth(),
    )
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run["run_id"]


def test_v1_created_at_filters_normalize_mixed_timezones_and_validate_order(client):
    token = _issue_token(client, "alice")
    target_model_id = _create_model_profile(client, token, "primary")
    run = _create_run(client, token, target_model_id, name="Timezone run")

    from medical_evals_api.database import get_session
    from medical_evals_api.repositories.evaluations import EvaluationRepository

    session = next(get_session())
    try:
        repo = EvaluationRepository(session)
        created_at = repo.get(run["run_id"]).created_at
    finally:
        session.close()

    after = (created_at - timedelta(minutes=1)).replace(tzinfo=None).isoformat()
    before = (created_at + timedelta(minutes=1)).replace(tzinfo=timezone.utc).isoformat()
    response = client.get(
        "/api/v1/evaluations",
        headers=_auth(token),
        params={"created_after": after, "created_before": before},
    )
    assert response.status_code == 200
    assert [item["run_id"] for item in response.json()] == [run["run_id"]]

    invalid = client.get(
        "/api/v1/evaluations",
        headers=_auth(token),
        params={
            "created_after": (created_at + timedelta(minutes=1)).replace(tzinfo=None).isoformat(),
            "created_before": (created_at - timedelta(minutes=1)).replace(tzinfo=timezone.utc).isoformat(),
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["message"] == "created_after must be earlier than created_before"


def test_v1_cancel_and_delete_regressions_do_not_overwrite_terminal_or_running_states(client):
    token = _issue_token(client, "alice")
    target_model_id = _create_model_profile(client, token, "primary")

    completed = _create_run(client, token, target_model_id, name="Completed run")
    _set_status(completed["run_id"], TaskStatus.COMPLETED)
    cancel = client.post(
        f"/api/v1/evaluations/{completed['run_id']}/cancel",
        headers=_auth(token),
    )
    assert cancel.status_code == 409

    detail = client.get(
        f"/api/v1/evaluations/{completed['run_id']}",
        headers=_auth(token),
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "succeeded"

    running = _create_run(client, token, target_model_id, name="Running run")
    _set_status(running["run_id"], TaskStatus.RUNNING)
    deleted = client.delete(
        f"/api/v1/evaluations/{running['run_id']}",
        headers=_auth(token),
    )
    assert deleted.status_code == 409

    running_detail = client.get(
        f"/api/v1/evaluations/{running['run_id']}",
        headers=_auth(token),
    )
    assert running_detail.status_code == 200
    assert running_detail.json()["status"] == "running"
