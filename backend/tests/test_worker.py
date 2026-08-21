from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.queue import LocalTaskQueue
from medical_evals_api.schemas.common import TaskStatus
from medical_evals_api.evaluator_adapter import DryRunEvaluationAdapter, OpenAICompatibleEvaluationAdapter
from medical_evals_api.worker import Worker


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


def test_worker_defaults_to_real_evaluation_adapter(tmp_path):
    assert isinstance(Worker(TaskRepository(tmp_path / "tasks.sqlite3")).adapter, OpenAICompatibleEvaluationAdapter)


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
