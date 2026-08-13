from medical_evals_api.repositories.tasks import TaskRepository
from medical_evals_api.services.reports import ReportService


def test_html_report_is_written_under_task_artifacts(tmp_path):
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task = repo.create(name="smoke", target_model_id="model", judge_model_id="judge", dataset_version_id="dataset-v1", rubric_id="rubric-v1")
    path = ReportService(repo, tmp_path / "artifacts").generate_html(task.task_id)
    assert path.exists()
    assert task.task_id in path.read_text()
