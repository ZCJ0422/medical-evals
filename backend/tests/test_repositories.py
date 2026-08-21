from concurrent.futures import ThreadPoolExecutor

from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.schemas.common import TaskProgress, TaskStatus


def test_task_repository_persists_queue_and_progress(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="smoke", target_model_id="model-a", judge_model_id="judge-a", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    assert task.status == TaskStatus.QUEUED
    repo.update_progress(task.task_id, TaskProgress(completed_count=1, total_count=2, progress_percent=50))
    repo.set_status(task.task_id, TaskStatus.RUNNING)
    loaded = repo.get(task.task_id)
    assert loaded is not None
    assert loaded.progress.completed_count == 1
    assert loaded.status == TaskStatus.RUNNING


def test_task_repository_claim_next_atomically_marks_task_running(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    first = repo.create(name="first", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")
    second = repo.create(name="second", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")

    claimed = repo.claim_next()

    assert claimed is not None
    assert claimed.task_id == first.task_id
    assert claimed.status == TaskStatus.RUNNING
    assert repo.claim_next().task_id == second.task_id
    assert repo.claim_next() is None


def test_task_repository_claim_assigns_and_renews_worker_lease(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="leased", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")

    claimed = repo.claim_next("worker-a", lease_seconds=60)

    assert claimed is not None
    assert claimed.lease_owner == "worker-a"
    assert claimed.lease_expires_at
    assert repo.renew_lease(task.task_id, "worker-a", lease_seconds=60)
    assert not repo.renew_lease(task.task_id, "worker-b", lease_seconds=60)


def test_two_worker_repositories_claim_distinct_tasks(tmp_path):
    database = tmp_path / "tasks.sqlite3"
    first_repo = TaskRepository(database)
    second_repo = TaskRepository(database)
    first_repo.create(name="first", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")
    first_repo.create(name="second", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")

    first_claim = first_repo.claim_next("worker-a")
    second_claim = second_repo.claim_next("worker-b")

    assert first_claim is not None
    assert second_claim is not None
    assert first_claim.task_id != second_claim.task_id
    assert first_claim.lease_owner == "worker-a"
    assert second_claim.lease_owner == "worker-b"


def test_concurrent_workers_claim_each_task_once(tmp_path):
    database = tmp_path / "tasks.sqlite3"
    seed = TaskRepository(database)
    for index in range(24):
        seed.create(name=f"task-{index}", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")

    def claim_for_worker(worker_number):
        repo = TaskRepository(database)
        claimed = []
        while True:
            task = repo.claim_next(f"worker-{worker_number}")
            if task is None:
                return claimed
            claimed.append((task.task_id, task.lease_owner))

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(claim_for_worker, range(6)))

    claims = [claim for worker_claims in results for claim in worker_claims]
    assert len(claims) == 24
    assert len({task_id for task_id, _ in claims}) == 24
    assert {owner for _, owner in claims} <= {f"worker-{index}" for index in range(6)}
    assert all(owner for _, owner in claims)


def test_expired_worker_lease_is_failed_and_cannot_be_completed_by_old_owner(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="expired", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")
    claimed = repo.claim_next("worker-a", lease_seconds=-1)
    assert claimed is not None

    assert repo.recover_expired_leases("lease expired") == 1
    recovered = repo.get(task.task_id)
    assert recovered is not None
    assert recovered.status == TaskStatus.FAILED
    assert repo.set_status_if_not_cancelled(task.task_id, TaskStatus.COMPLETED, worker_id="worker-a").status == TaskStatus.FAILED


def test_task_result_requires_current_worker_lease(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="result lease", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")
    repo.claim_next("worker-a")

    try:
        repo.save_result(
            task.task_id,
            total_score=1.0,
            dimension_scores={"accuracy": 1.0},
            error_categories={},
            completed_count=1,
            failed_count=0,
            retry_count=0,
            worker_id="worker-b",
        )
    except RuntimeError as error:
        assert str(error) == "Worker lease lost while saving task result"
    else:
        raise AssertionError("a non-owner must not save a task result")


def test_terminal_status_does_not_overwrite_cancellation(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="cancelled", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")
    repo.set_status(task.task_id, TaskStatus.CANCELLED)

    result = repo.set_status_if_not_cancelled(task.task_id, TaskStatus.COMPLETED)

    assert result.status == TaskStatus.CANCELLED
    assert repo.get(task.task_id).status == TaskStatus.CANCELLED


def test_recover_interrupted_tasks_marks_running_tasks_failed(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    running = repo.create(name="running", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")
    queued = repo.create(name="queued", target_model_id="model", judge_model_id="", dataset_version_id="dataset", rubric_id="rubric")
    repo.set_status(running.task_id, TaskStatus.RUNNING)

    recovered = repo.recover_interrupted_tasks("worker interrupted")

    assert recovered == 1
    recovered_task = repo.get(running.task_id)
    assert recovered_task is not None
    assert recovered_task.status == TaskStatus.FAILED
    assert recovered_task.error == "worker interrupted"
    assert repo.get(queued.task_id).status == TaskStatus.QUEUED


def test_task_repository_persists_credential_environment_names(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(
        name="env credentials",
        target_model_id="model",
        judge_model_id="judge",
        dataset_version_id="dataset",
        rubric_id="rubric",
        target_api_key_env="TARGET_KEY",
        judge_api_key_env="JUDGE_KEY",
    )

    loaded = repo.get(task.task_id)

    assert loaded is not None
    assert loaded.target_api_key_env == "TARGET_KEY"
    assert loaded.judge_api_key_env == "JUDGE_KEY"
