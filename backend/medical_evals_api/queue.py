from typing import Protocol

from .repositories.tasks import TaskRepository
from .schemas.common import TaskStatus


class TaskQueue(Protocol):
    """Queue boundary shared by the Worker loop and queue implementations."""

    def enqueue(self, task_id: str) -> None:
        ...

    def claim_next(self, worker_id: str = "", lease_seconds: int = 300) -> str | None:
        ...


class LocalTaskQueue:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    def enqueue(self, task_id: str) -> None:
        task = self.repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status != TaskStatus.QUEUED:
            raise ValueError("only queued tasks can be enqueued")

    def claim_next(self, worker_id: str = "", lease_seconds: int = 300) -> str | None:
        task = self.repository.claim_next(worker_id, lease_seconds)
        return task.task_id if task else None
