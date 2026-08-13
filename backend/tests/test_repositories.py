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
