from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationSummary:
    task_id: str
    total_score: float
    dimension_scores: dict[str, float]
    pass_rate: float
    error_categories: dict[str, int]
    completed_count: int
    failed_count: int
    retry_count: int


class ResultService:
    def __init__(self, repository):
        self.repository = repository

    def get_public_summary(self, task_id: str) -> EvaluationSummary:
        task = self.repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        completed = task.progress.completed_count
        failed = task.progress.failed_count
        return EvaluationSummary(task_id, 0.0, {}, 0.0, {}, completed, failed, task.progress.retry_count)
