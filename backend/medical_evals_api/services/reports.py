from pathlib import Path

from .results import ResultService


class ReportService:
    def __init__(self, repository, artifact_dir: Path):
        self.repository = repository
        self.artifact_dir = artifact_dir

    def generate_html(self, task_id: str) -> Path:
        summary = ResultService(self.repository).get_public_summary(task_id)
        task_dir = self.artifact_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        target = task_dir / "report.html"
        target.write_text(f"<html><body><h1>Medical Evals Report</h1><p>Task: {summary.task_id}</p><p>Total score: {summary.total_score:.2f}</p></body></html>", encoding="utf-8")
        return target
