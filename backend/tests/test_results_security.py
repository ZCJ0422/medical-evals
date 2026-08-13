from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.services.results import ResultService


def test_public_summary_contains_aggregates_only(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="smoke", target_model_id="model", judge_model_id="judge", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    summary = ResultService(repo).get_public_summary(task.task_id)
    assert not hasattr(summary, "question")
    assert not hasattr(summary, "standard_answer")
