from medical_evals_api.config import settings
from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.schemas.common import TaskStatus
from medical_evals_api.evaluator_adapter import DryRunEvaluationAdapter
from medical_evals_api.worker import Worker


def test_max_samples_limits_worker_dataset(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="limited", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default", max_samples=2)
    result = Worker(repo, adapter=DryRunEvaluationAdapter()).run_task(task.task_id)
    assert result.progress.total_count == 2


def test_delete_task_removes_task_and_result(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="delete me", target_model_id="target", judge_model_id="judge", dataset_version_id="medical-medqa.dev.v1", rubric_id="medical-medqa.default")
    repo.save_result(task.task_id, total_score=1, dimension_scores={}, error_categories={}, completed_count=1, failed_count=0, retry_count=0)
    assert repo.delete(task.task_id) is True
    assert repo.get(task.task_id) is None
    assert repo.get_result(task.task_id) is None
