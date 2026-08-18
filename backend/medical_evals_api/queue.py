from .repositories.tasks import TaskRepository
from .schemas.common import TaskStatus


class LocalTaskQueue:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    def enqueue(self, task_id: str) -> None:
        task = self.repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status != TaskStatus.QUEUED:
            raise ValueError("only queued tasks can be enqueued")

    def claim_next(self) -> str | None:
        task = self.repository.next_queued()
        return task.task_id if task else None
