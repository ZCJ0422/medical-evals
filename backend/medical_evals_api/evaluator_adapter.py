from collections.abc import Callable
from dataclasses import dataclass

from .models import EvaluationTask
from .schemas.common import TaskProgress


@dataclass(frozen=True)
class EvaluationRunResult:
    success_count: int
    failed_count: int
    retry_count: int
    total_count: int


class EvaluationAdapter:
    def run(self, task: EvaluationTask, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult:
        raise NotImplementedError


class DryRunEvaluationAdapter(EvaluationAdapter):
    def run(self, task: EvaluationTask, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult:
        total = task.progress.total_count or 1
        for completed in range(1, total + 1):
            if is_cancelled():
                break
            on_progress(TaskProgress(completed_count=completed, total_count=total, progress_percent=completed / total * 100, success_count=completed))
        return EvaluationRunResult(success_count=total, failed_count=0, retry_count=0, total_count=total)
