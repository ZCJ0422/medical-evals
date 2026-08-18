from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationSummary:
    task_id: str
    name: str
    status: str
    dataset_version_id: str
    target_model_id: str
    judge_model_id: str
    created_at: str
    updated_at: str
    error: str | None
    stage: str
    progress_percent: float
    total_score: float
    dimension_scores: dict[str, float]
    accuracy: float
    parse_success_rate: float | None
    request_success_count: int
    parse_failed_count: int
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
        stored = self.repository.get_result(task_id)
        completed = stored["completed_count"] if stored else task.progress.completed_count
        failed = stored["failed_count"] if stored else task.progress.failed_count
        total_score = stored["total_score"] if stored else 0.0
        dimensions = stored["dimension_scores"] if stored else {}
        errors = stored["error_categories"] if stored else {}
        retries = stored["retry_count"] if stored else task.progress.retry_count
        accuracy = stored["accuracy"] if stored else total_score
        parse_success_rate = stored["parse_success_rate"] if stored else None
        request_success_count = stored["request_success_count"] if stored else task.progress.success_count
        parse_failed_count = stored["parse_failed_count"] if stored else 0
        return EvaluationSummary(
            task_id,
            task.name,
            task.status.value,
            task.dataset_version_id,
            task.target_model_id,
            task.judge_model_id,
            task.created_at,
            task.updated_at,
            task.error,
            task.progress.stage,
            task.progress.progress_percent,
            total_score,
            dimensions,
            accuracy,
            parse_success_rate,
            request_success_count,
            parse_failed_count,
            errors,
            completed,
            failed,
            retries,
        )
