from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
import redis
from fastapi.testclient import TestClient

from medical_evals_api.config import settings
from medical_evals_api.database import get_session, upgrade_database
from medical_evals_api.evaluator_adapter import DryRunEvaluationAdapter
from medical_evals_api.main import app
from medical_evals_api.redis_queue import RedisTaskQueue
from medical_evals_api.repositories.evaluations import EvaluationRepository
from medical_evals_api.schemas.common import TaskStatus
from medical_evals_api.worker import Worker


pytestmark = pytest.mark.integration


@pytest.fixture
def integration_client(tmp_path, monkeypatch):
    database_url = os.getenv("MEDICAL_EVALS_TEST_POSTGRES_URL")
    redis_url = os.getenv("MEDICAL_EVALS_TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("requires MEDICAL_EVALS_TEST_POSTGRES_URL and MEDICAL_EVALS_TEST_REDIS_URL")

    from medical_evals_api import database

    monkeypatch.setattr(settings, "database_url", database_url)
    monkeypatch.setattr(settings, "redis_url", redis_url)
    monkeypatch.setattr(settings, "artifact_dir", Path(tmp_path) / "artifacts")
    database._build_engine.cache_clear()
    database._build_session_factory.cache_clear()
    database._build_redis.cache_clear()
    upgrade_database(settings)
    with TestClient(app) as client:
        yield client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "correct horse battery staple"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _create_model(client: TestClient, token: str, name: str) -> str:
    response = client.post(
        "/api/v1/models",
        headers=_auth(token),
        json={
            "name": name,
            "base_url": "https://example.test/v1",
            "model_name": f"{name.lower()}-model",
            "api_key": f"sk-{uuid4().hex}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_run(client: TestClient, token: str, model_id: str, name: str) -> dict:
    response = client.post(
        "/api/v1/evaluations",
        headers=_auth(token),
        json={
            "name": name,
            "evaluation_definition_id": "medqa",
            "target_model_id": model_id,
            "split": "dev",
            "sample_limit": 1,
            "config": {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_postgres_redis_evaluation_lifecycle_and_user_isolation(integration_client, monkeypatch):
    client = integration_client
    alice = _register(client, f"alice-{uuid4().hex[:8]}")
    bob = _register(client, f"bob-{uuid4().hex[:8]}")
    alice_model = _create_model(client, alice, "alice-primary")
    bob_model = _create_model(client, bob, "bob-primary")

    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    queue = RedisTaskQueue(
        redis_client,
        stream_key=f"medical-evals:integration:{uuid4().hex}",
        group_name=f"integration-workers-{uuid4().hex}",
        dedupe_prefix=f"medical-evals:integration:dedupe:{uuid4().hex}",
    )
    monkeypatch.setattr(
        "medical_evals_api.routes.evaluations._enqueue_visible_run",
        lambda _repo, run_id: queue.enqueue(run_id),
    )

    run = _create_run(client, alice, alice_model, "integration-medqa")
    run_id = run["run_id"]
    assert run["status"] == "queued"
    assert client.get(f"/api/v1/evaluations/{run_id}", headers=_auth(bob)).status_code == 404
    bob_models = client.get("/api/v1/models", headers=_auth(bob)).json()
    assert [item["id"] for item in bob_models] == [bob_model]

    claim = queue.claim_next(worker_id="integration-worker", lease_seconds=300, block_ms=100)
    assert claim is not None and claim.run_id == run_id
    session = next(get_session(settings))
    try:
        repository = EvaluationRepository(session, settings.artifact_dir)
        finished = Worker(
            repository,
            adapter=DryRunEvaluationAdapter(),
            worker_id="integration-worker",
        ).run_task(run_id, claim)
        assert finished.status == TaskStatus.COMPLETED
    finally:
        session.close()
        redis_client.delete(queue._dedupe_key(run_id))

    summary = client.get(f"/api/v1/evaluations/{run_id}/summary", headers=_auth(alice))
    assert summary.status_code == 200, summary.text
    assert summary.json()["status"] == "succeeded"
    assert client.get(f"/api/v1/evaluations/{run_id}/summary", headers=_auth(bob)).status_code == 404

    cancelled = _create_run(client, alice, alice_model, "cancel-and-retry")
    cancel_response = client.post(
        f"/api/v1/evaluations/{cancelled['run_id']}/cancel",
        headers=_auth(alice),
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    retry_response = client.post(
        f"/api/v1/evaluations/{cancelled['run_id']}/retry",
        headers=_auth(alice),
    )
    assert retry_response.status_code == 201
    assert retry_response.json()["retry_of_run_id"] == cancelled["run_id"]
