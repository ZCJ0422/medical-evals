from dataclasses import replace

import pytest

from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.queue import LocalTaskQueue, QueueClaim
from medical_evals_api.schemas.common import TaskStatus
from medical_evals_api.evaluator_adapter import DryRunEvaluationAdapter, OpenAICompatibleEvaluationAdapter
from medical_evals_api.worker import Worker
from medical_evals_api.evaluator_adapter import _resolve_task_secret


class FailingAdapter:
    def run(self, task, on_progress, is_cancelled):
        raise RuntimeError("missing API key")


class PartialAdapter:
    def run(self, task, on_progress, is_cancelled):
        from medical_evals_api.evaluator_adapter import EvaluationRunResult
        return EvaluationRunResult(success_count=0, failed_count=5, retry_count=0, total_count=5, error_categories={"request_error": 5})


class StagedAdapter:
    def run(self, task, on_progress, is_cancelled):
        self.on_stage("target_model")
        on_progress(__import__("medical_evals_api.schemas.common", fromlist=["TaskProgress"]).TaskProgress(completed_count=1, total_count=1, progress_percent=100, success_count=1))
        from medical_evals_api.evaluator_adapter import EvaluationRunResult
        return EvaluationRunResult(success_count=1, failed_count=0, retry_count=0, total_count=1)


class FakeQueue:
    def __init__(self, claims=None):
        self.claims = list(claims or [])
        self.heartbeats = []
        self.acked = []
        self.reconciled = []

    def enqueue(self, task_id: str) -> None:
        del task_id

    def claim_next(self, worker_id: str = "", lease_seconds: int = 300, block_ms: int = 1000):
        del worker_id, lease_seconds, block_ms
        if self.claims:
            return self.claims.pop(0)
        raise KeyboardInterrupt()

    def heartbeat(self, claim: QueueClaim) -> None:
        self.heartbeats.append(claim)

    def ack(self, claim: QueueClaim) -> None:
        self.acked.append(claim)

    def reconcile(self, run_ids) -> int:
        run_ids = list(run_ids)
        self.reconciled.append(run_ids)
        return len(run_ids)


class LeaseLosingRepository:
    def __init__(self, task, artifact_root):
        self.task = task
        self.artifact_root = artifact_root
        self.progress_updates = []
        self.saved_results = []

    def get(self, task_id: str):
        return self.task if self.task.task_id == task_id else None

    def renew_lease(self, task_id: str, worker_id: str, lease_seconds: int = 300) -> bool:
        del task_id, worker_id, lease_seconds
        return False

    def update_progress(self, task_id, progress, worker_id=""):
        del worker_id
        self.progress_updates.append(progress)
        self.task = replace(self.task, progress=progress)
        return self.task

    def set_status(self, task_id, status, error=None):
        del task_id
        self.task = replace(self.task, status=status, error=error)
        return self.task

    def set_status_if_not_cancelled(self, task_id, status, error=None, worker_id=""):
        del task_id, status, error, worker_id
        return self.task

    def save_result(self, task_id, **payload):
        del task_id
        self.saved_results.append(payload)

    def recover_expired_leases(self, error: str) -> list[str]:
        del error
        return []

    def recover_interrupted_tasks(self, error: str) -> int:
        del error
        return 0

    def list_queued_run_ids(self):
        return []


class ClaimedTaskRepository:
    def __init__(self, task, artifact_root, expired_run_ids=None, queued_run_ids=None):
        self.task = task
        self.artifact_root = artifact_root
        self.claimed = []
        self.recovered_expired = []
        self.recovered_interrupted = 0
        self.expired_run_ids = list(expired_run_ids or [])
        self.queued_run_ids = list(queued_run_ids or [])

    def get(self, task_id: str):
        return self.task if self.task.task_id == task_id else None

    def claim(self, run_id: str, worker_id: str, lease_seconds: int = 300):
        del lease_seconds
        if run_id != self.task.task_id or self.task.status != TaskStatus.QUEUED:
            return None
        self.claimed.append((run_id, worker_id))
        self.task = replace(self.task, status=TaskStatus.RUNNING, lease_owner=worker_id)
        return self.task

    def renew_lease(self, task_id: str, worker_id: str, lease_seconds: int = 300) -> bool:
        del task_id, lease_seconds
        return self.task.status == TaskStatus.RUNNING and self.task.lease_owner == worker_id

    def update_progress(self, task_id, progress, worker_id=""):
        del task_id, worker_id
        self.task = replace(self.task, progress=progress)
        return self.task

    def set_status(self, task_id, status, error=None):
        del task_id
        self.task = replace(self.task, status=status, error=error)
        return self.task

    def set_status_if_not_cancelled(self, task_id, status, error=None, worker_id=""):
        del task_id, worker_id
        self.task = replace(self.task, status=status, error=error)
        return self.task

    def save_result(self, task_id, **payload):
        del task_id, payload

    def recover_expired_leases(self, error: str) -> list[str]:
        del error
        self.recovered_expired.append(True)
        return list(self.expired_run_ids)

    def recover_interrupted_tasks(self, error: str) -> int:
        del error
        self.recovered_interrupted += 1
        return 0

    def list_queued_run_ids(self):
        if self.queued_run_ids:
            return list(self.queued_run_ids)
        if self.task.status == TaskStatus.QUEUED:
            return [self.task.task_id]
        return []


def test_worker_defaults_to_real_evaluation_adapter(tmp_path):
    assert isinstance(Worker(TaskRepository(tmp_path / "tasks.sqlite3")).adapter, OpenAICompatibleEvaluationAdapter)


def test_task_secret_resolution_prefers_encrypted_value_and_supports_env_fallback(monkeypatch):
    monkeypatch.setenv("TARGET_KEY", "from-environment")

    assert _resolve_task_secret("", "TARGET_KEY") == "from-environment"


def test_worker_completes_dry_run(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="smoke", target_model_id="model", judge_model_id="judge", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    result = Worker(repo, adapter=DryRunEvaluationAdapter()).run_task(task.task_id)
    assert result.status == TaskStatus.COMPLETED
    assert result.progress.progress_percent == 100


def test_worker_runs_a_task_claimed_by_local_queue(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="claimed", target_model_id="model", judge_model_id="judge", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    claimed_id = LocalTaskQueue(repo).claim_next()

    assert claimed_id == task.task_id
    result = Worker(repo, adapter=DryRunEvaluationAdapter()).run_task(claimed_id)

    assert result.status == TaskStatus.COMPLETED


def test_worker_marks_unhandled_adapter_error_as_failed(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="fails", target_model_id="model", judge_model_id="judge", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    result = Worker(repo, adapter=FailingAdapter()).run_task(task.task_id)
    assert result.status == TaskStatus.FAILED
    assert result.error == "missing API key"


def test_worker_persists_successful_count_separately_from_attempted_count(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="partial", target_model_id="model", judge_model_id="judge", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    Worker(repo, adapter=PartialAdapter()).run_task(task.task_id)
    saved = repo.get_result(task.task_id)
    assert saved is not None
    assert saved["completed_count"] == 0
    assert saved["failed_count"] == 5


def test_worker_tracks_execution_stage_until_completion(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="staged", target_model_id="model", judge_model_id="judge", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    adapter = StagedAdapter()

    result = Worker(repo, adapter=adapter).run_task(task.task_id)

    assert result.status == TaskStatus.COMPLETED
    assert repo.get(task.task_id).progress.stage == "completed"


def test_worker_acks_queue_claim_after_durable_completion(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="claimed", target_model_id="model", judge_model_id="", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    repo.claim_next("worker-a", lease_seconds=60)
    queue_claim = QueueClaim(run_id=task.task_id, message_id="1-0", consumer="worker-a")
    queue = FakeQueue()
    worker = Worker(repo, adapter=DryRunEvaluationAdapter(), worker_id="worker-a", lease_seconds=60)
    worker.queue = queue

    result = worker.run_task(task.task_id, queue_claim)

    assert result.status == TaskStatus.COMPLETED
    assert queue.acked == [queue_claim]
    assert queue.heartbeats


def test_worker_does_not_ack_when_lease_is_lost(tmp_path):
    base_repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = base_repo.create(name="lease-loss", target_model_id="model", judge_model_id="", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    claimed = base_repo.claim_next("worker-a", lease_seconds=60)
    assert claimed is not None
    queue_claim = QueueClaim(run_id=task.task_id, message_id="1-0", consumer="worker-a")
    queue = FakeQueue()
    repository = LeaseLosingRepository(claimed, tmp_path / "artifacts")
    worker = Worker(repository, adapter=StagedAdapter(), worker_id="worker-a", lease_seconds=60)
    worker.queue = queue

    result = worker.run_task(task.task_id, queue_claim)

    assert result.status == TaskStatus.RUNNING
    assert queue.acked == []
    assert queue.heartbeats == []


def test_worker_run_forever_reconciles_and_processes_queue_claim(tmp_path):
    base_repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = base_repo.create(name="loop", target_model_id="model", judge_model_id="", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    queue_claim = QueueClaim(run_id=task.task_id, message_id="1-0", consumer="worker-a")
    queue = FakeQueue(claims=[queue_claim])

    def repository_factory():
        current = base_repo.get(task.task_id)
        assert current is not None
        return ClaimedTaskRepository(current, tmp_path / "artifacts")

    worker = Worker(base_repo, adapter=DryRunEvaluationAdapter(), worker_id="worker-a", lease_seconds=60)

    with pytest.raises(KeyboardInterrupt):
        worker.run_forever(queue, repository_factory, idle_seconds=0)

    assert queue.reconciled[0] == [task.task_id]
    assert queue.acked == [queue_claim]


def test_worker_run_forever_requeues_expired_leases_via_reconciliation(tmp_path):
    base_repo = TaskRepository(tmp_path / "tasks.sqlite3")
    expired = base_repo.create(
        name="expired",
        target_model_id="model",
        judge_model_id="",
        dataset_version_id="dataset-v1",
        rubric_id="rubric-v1",
    )
    additional = base_repo.create(
        name="queued",
        target_model_id="model",
        judge_model_id="",
        dataset_version_id="dataset-v1",
        rubric_id="rubric-v1",
    )
    queue = FakeQueue()

    def repository_factory():
        current = base_repo.get(expired.task_id)
        assert current is not None
        return ClaimedTaskRepository(
            current,
            tmp_path / "artifacts",
            expired_run_ids=[expired.task_id],
            queued_run_ids=[expired.task_id, additional.task_id],
        )

    worker = Worker(base_repo, adapter=DryRunEvaluationAdapter(), worker_id="worker-a", lease_seconds=60)

    with pytest.raises(KeyboardInterrupt):
        worker.run_forever(queue, repository_factory, idle_seconds=0)

    assert queue.reconciled[0] == [expired.task_id, additional.task_id]


def test_completed_run_manifest_matches_final_artifacts(tmp_path):
    import hashlib
    import json

    repo = TaskRepository(tmp_path / "tasks.sqlite3", tmp_path / "artifacts")
    task = repo.create(name="Manifest regression", target_model_id="fixture", judge_model_id="", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default", max_samples=1)
    Worker(repo, adapter=DryRunEvaluationAdapter()).run_task(task.task_id)
    directory = repo.artifact_root / task.task_id
    manifest = json.loads((directory / "manifest.json").read_text())
    entries = {entry["name"]: entry for entry in manifest["files"]}
    assert {"summary.json", "run.log", "events.jsonl"} <= entries.keys()
    assert "Run completed" in (directory / "run.log").read_text()
    for name, entry in entries.items():
        content = (directory / name).read_bytes()
        assert entry["size_bytes"] == len(content)
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
