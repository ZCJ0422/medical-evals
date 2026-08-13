from .evaluator_adapter import DryRunEvaluationAdapter, EvaluationAdapter
from .models import EvaluationTask
from .repositories.tasks import TaskRepository
from .schemas.common import TaskProgress, TaskStatus


class Worker:
    def __init__(self, repository: TaskRepository, adapter: EvaluationAdapter | None = None):
        self.repository = repository
        self.adapter = adapter or DryRunEvaluationAdapter()

    def run_task(self, task_id: str) -> EvaluationTask:
        task = self.repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status != TaskStatus.QUEUED:
            return task
        self.repository.set_status(task_id, TaskStatus.RUNNING)
        result = self.adapter.run(task, lambda progress: self.repository.update_progress(task_id, progress), lambda: self.repository.get(task_id).status == TaskStatus.CANCELLED)
        current = self.repository.get(task_id)
        if current is not None and current.status == TaskStatus.CANCELLED:
            return current
        final = TaskProgress(completed_count=result.total_count, total_count=result.total_count, progress_percent=100, success_count=result.success_count, failed_count=result.failed_count, retry_count=result.retry_count)
        self.repository.update_progress(task_id, final)
        return self.repository.set_status(task_id, TaskStatus.PARTIAL_FAILED if result.failed_count else TaskStatus.COMPLETED)
