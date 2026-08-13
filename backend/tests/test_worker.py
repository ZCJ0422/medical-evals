from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.schemas.common import TaskStatus
from medical_evals_api.worker import Worker


def test_worker_completes_dry_run(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="smoke", target_model_id="model", judge_model_id="judge", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    result = Worker(repo).run_task(task.task_id)
    assert result.status == TaskStatus.COMPLETED
    assert result.progress.progress_percent == 100
