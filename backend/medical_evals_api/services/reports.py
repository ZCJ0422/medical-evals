from pathlib import Path

from .results import ResultService
from ..artifacts import ArtifactWriter


class ReportService:
    def __init__(self, repository, artifact_dir: Path):
        self.repository = repository
        self.artifact_dir = artifact_dir

    def generate_html(self, task_id: str) -> Path:
        summary = ResultService(self.repository).get_public_summary(task_id)
        task_dir = self.artifact_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        target = task_dir / "report.html"
        parse_rate = "N/A" if summary.parse_success_rate is None else f"{summary.parse_success_rate:.2f}"
        target.write_text(f"<html><body><h1>Medical Evals Report</h1><p>Task: {summary.task_id}</p><p>Answer accuracy: {summary.accuracy:.2f}</p><p>Parse success rate: {parse_rate}</p></body></html>", encoding="utf-8")
        ArtifactWriter(self.artifact_dir, task_id).finalize()
        return target
