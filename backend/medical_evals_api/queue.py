from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from redis.exceptions import RedisError

from .schemas.common import TaskStatus


@dataclass(frozen=True)
class QueueClaim:
    run_id: str
    message_id: str
    consumer: str


class TaskQueue(Protocol):
    """Queue boundary shared by the Worker loop and queue implementations."""

    def enqueue(self, task_id: str) -> None:
        ...

    def claim_next(
        self,
        worker_id: str = "",
        lease_seconds: int = 300,
        block_ms: int = 1000,
    ) -> QueueClaim | None:
        ...

    def heartbeat(self, claim: QueueClaim) -> None:
        ...

    def ack(self, claim: QueueClaim) -> None:
        ...

    def reconcile(self, run_ids: Sequence[str]) -> int:
        ...


class LocalTaskQueue:
    """Compatibility wrapper for legacy tests and route-side enqueue calls.

    The v1 PostgreSQL worker path uses RedisTaskQueue directly. This wrapper
    keeps older SQLite-backed tests working while letting route code continue to
    call `LocalTaskQueue(repo).enqueue(...)` without learning the Redis details.
    """

    def __init__(self, repository, redis_client=None):
        self.repository = repository
        self.redis_client = redis_client
        self._delegate = None

    def _is_legacy_repository(self) -> bool:
        return not hasattr(self.repository, "session")

    def _redis_delegate(self):
        if self._delegate is None:
            from .database import get_redis
            from .redis_queue import RedisTaskQueue

            self._delegate = RedisTaskQueue(
                self.redis_client or get_redis(),
                repository=self.repository,
            )
        return self._delegate

    def enqueue(self, task_id: str) -> None:
        task = self.repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status != TaskStatus.QUEUED:
            raise ValueError("only queued tasks can be enqueued")
        if self._is_legacy_repository():
            return
        try:
            self._redis_delegate().enqueue(task_id)
        except RedisError:
            # PostgreSQL remains the source of truth; a later Worker reconcile can
            # repopulate Redis after the outage clears.
            return

    def claim_next(self, worker_id: str = "", lease_seconds: int = 300) -> str | None:
        if self._is_legacy_repository():
            task = self.repository.claim_next(worker_id, lease_seconds)
            return task.task_id if task else None
        try:
            claim = self._redis_delegate().claim_next(
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                block_ms=0,
            )
        except RedisError:
            return None
        return claim.run_id if claim else None
