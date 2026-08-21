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
