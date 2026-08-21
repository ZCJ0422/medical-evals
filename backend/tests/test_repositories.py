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
