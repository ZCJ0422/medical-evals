from __future__ import annotations

from collections.abc import Mapping, Sequence

from redis.exceptions import ResponseError

from .queue import QueueClaim
from .schemas.common import TaskStatus


ENQUEUE_LUA = """
if redis.call('GET', KEYS[2]) then
  return redis.call('GET', KEYS[2])
end
local message_id = redis.call('XADD', KEYS[1], '*', 'run_id', ARGV[1])
redis.call('SET', KEYS[2], message_id)
return message_id
"""

ACK_LUA = """
redis.call('XACK', KEYS[1], ARGV[1], ARGV[2])
redis.call('XDEL', KEYS[1], ARGV[2])
if redis.call('GET', KEYS[2]) == ARGV[2] then
  redis.call('DEL', KEYS[2])
end
return 1
"""


def _decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


class RedisTaskQueue:
    def __init__(
        self,
        redis_client,
        repository=None,
        *,
        stream_key: str = "medical-evals:evaluations",
        group_name: str = "medical-evals-workers",
        dedupe_prefix: str = "medical-evals:evaluations:dedupe",
        reclaim_grace_seconds: int = 30,
    ):
        self.redis = redis_client
        self.repository = repository
        self.stream_key = stream_key
        self.group_name = group_name
        self.dedupe_prefix = dedupe_prefix
        self.reclaim_grace_seconds = reclaim_grace_seconds

    def _dedupe_key(self, run_id: str) -> str:
        return f"{self.dedupe_prefix}:{run_id}"

    def _ensure_group(self) -> None:
        try:
            self.redis.xgroup_create(
                name=self.stream_key,
                groupname=self.group_name,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def _validate_queued(self, run_id: str) -> None:
        if self.repository is None:
            return
        task = self.repository.get(run_id)
        if task is None:
            raise KeyError(run_id)
        if task.status != TaskStatus.QUEUED:
            raise ValueError("only queued tasks can be enqueued")

    def enqueue(self, run_id: str) -> None:
        self._validate_queued(run_id)
        self._ensure_group()
        self.redis.eval(
            ENQUEUE_LUA,
            2,
            self.stream_key,
            self._dedupe_key(run_id),
            run_id,
        )

    def _claim_from_messages(self, messages, consumer: str) -> QueueClaim | None:
        if not messages:
            return None
        message_id, payload = messages[0]
        fields = {_decode(key): _decode(value) for key, value in dict(payload).items()}
        run_id = fields.get("run_id", "")
        if not run_id:
            return None
        return QueueClaim(
            run_id=run_id,
            message_id=_decode(message_id),
            consumer=consumer,
        )

    def _claim_stale(
        self,
        consumer: str,
        *,
        lease_seconds: int,
    ) -> QueueClaim | None:
        min_idle_ms = max(
            1000,
            (lease_seconds + self.reclaim_grace_seconds) * 1000,
        )
        result = self.redis.xautoclaim(
            self.stream_key,
            self.group_name,
            consumer,
            min_idle_ms,
            start_id="0-0",
            count=1,
        )
        messages = result[1] if isinstance(result, (list, tuple)) and len(result) >= 2 else []
        return self._claim_from_messages(messages, consumer)

    def claim_next(
        self,
        worker_id: str = "",
        lease_seconds: int = 300,
        block_ms: int = 1000,
    ) -> QueueClaim | None:
        self._ensure_group()
        consumer = worker_id or "worker"
        stale = self._claim_stale(consumer, lease_seconds=lease_seconds)
        if stale is not None:
            return stale
        response = self.redis.xreadgroup(
            groupname=self.group_name,
            consumername=consumer,
            streams={self.stream_key: ">"},
            count=1,
            block=block_ms,
        )
        if not response:
            return None
        _, messages = response[0]
        return self._claim_from_messages(messages, consumer)

    def heartbeat(self, claim: QueueClaim) -> None:
        self.redis.xclaim(
            self.stream_key,
            self.group_name,
            claim.consumer,
            min_idle_time=0,
            message_ids=[claim.message_id],
            idle=0,
        )

    def ack(self, claim: QueueClaim) -> None:
        self.redis.eval(
            ACK_LUA,
            2,
            self.stream_key,
            self._dedupe_key(claim.run_id),
            self.group_name,
            claim.message_id,
        )

    def reconcile(self, run_ids: Sequence[str]) -> int:
        self._ensure_group()
        newly_visible = 0
        for run_id in run_ids:
            if self.repository is None:
                previous = _decode(self.redis.get(self._dedupe_key(run_id)))
                self.redis.eval(
                    ENQUEUE_LUA,
                    2,
                    self.stream_key,
                    self._dedupe_key(run_id),
                    run_id,
                )
                if previous is None:
                    newly_visible += 1
                continue
            task = self.repository.get(run_id)
            if task is None or task.status != TaskStatus.QUEUED:
                continue
            previous = _decode(self.redis.get(self._dedupe_key(run_id)))
            self.enqueue(run_id)
            if previous is None:
                newly_visible += 1
        return newly_visible
