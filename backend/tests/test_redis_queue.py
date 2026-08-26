import os
from dataclasses import dataclass
from uuid import uuid4

import pytest
import redis

from medical_evals_api.queue import LocalTaskQueue
from medical_evals_api.redis_queue import ACK_LUA, ENQUEUE_LUA, RedisTaskQueue
from medical_evals_api.schemas.common import TaskStatus


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.streams = {}
        self.groups = {}
        self._counter = 0
        self.now_ms = 0

    def advance(self, milliseconds: int) -> None:
        self.now_ms += milliseconds

    def ping(self) -> bool:
        return True

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0

    def xgroup_create(self, name: str, groupname: str, id: str = "0-0", mkstream: bool = False):
        del id
        if mkstream and name not in self.streams:
            self.streams[name] = []
        groups = self.groups.setdefault(name, {})
        if groupname in groups:
            raise redis.exceptions.ResponseError("BUSYGROUP Consumer Group name already exists")
        groups[groupname] = {"cursor": 0, "pending": {}}

    def xadd(self, name: str, fields: dict[str, str]) -> str:
        self._counter += 1
        message_id = f"{self._counter}-0"
        self.streams.setdefault(name, []).append((message_id, dict(fields)))
        return message_id

    def xreadgroup(
        self,
        *,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int = 1,
        block: int | None = None,
    ):
        del block, count
        stream_name, stream_id = next(iter(streams.items()))
        assert stream_id == ">"
        group = self.groups[stream_name][groupname]
        stream = self.streams.get(stream_name, [])
        for index in range(group["cursor"], len(stream)):
            message = stream[index]
            group["cursor"] = index + 1
            if message is None:
                continue
            message_id, payload = message
            group["pending"][message_id] = {
                "consumer": consumername,
                "payload": dict(payload),
                "delivered_at": self.now_ms,
            }
            return [(stream_name, [(message_id, dict(payload))])]
        return []

    def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        *,
        start_id: str = "0-0",
        count: int = 1,
    ):
        del start_id, count
        group = self.groups[name][groupname]
        claimed = []
        for message in self.streams.get(name, []):
            if message is None:
                continue
            message_id, payload = message
            pending = group["pending"].get(message_id)
            if pending is None:
                continue
            if self.now_ms - pending["delivered_at"] < min_idle_time:
                continue
            pending["consumer"] = consumername
            pending["delivered_at"] = self.now_ms
            claimed.append((message_id, dict(payload)))
            break
        return ("0-0", claimed, [])

    def xclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        message_ids: list[str],
        *,
        idle: int = 0,
    ):
        del min_idle_time
        group = self.groups[name][groupname]
        claimed = []
        for message_id in message_ids:
            pending = group["pending"].get(message_id)
            if pending is None:
                continue
            pending["consumer"] = consumername
            pending["delivered_at"] = self.now_ms - idle
            claimed.append((message_id, dict(pending["payload"])))
        return claimed

    def xack(self, name: str, groupname: str, message_id: str) -> int:
        del name
        group = self.groups[next(iter(self.groups))][groupname]
        return 1 if group["pending"].pop(message_id, None) is not None else 0

    def xdel(self, name: str, message_id: str) -> int:
        stream = self.streams.get(name, [])
        for index, message in enumerate(stream):
            if message is None:
                continue
            current_id, _ = message
            if current_id == message_id:
                stream[index] = None
                return 1
        return 0

    def eval(self, script: str, numkeys: int, *keys_and_args):
        del numkeys
        if script == ENQUEUE_LUA:
            stream_key, dedupe_key, run_id = keys_and_args
            existing = self.get(dedupe_key)
            if existing:
                return existing
            message_id = self.xadd(stream_key, {"run_id": run_id})
            self.set(dedupe_key, message_id)
            return message_id
        if script == ACK_LUA:
            stream_key, dedupe_key, group_name, message_id = keys_and_args
            self.xack(stream_key, group_name, message_id)
            self.xdel(stream_key, message_id)
            if self.get(dedupe_key) == message_id:
                self.delete(dedupe_key)
            return 1
        raise AssertionError("unexpected eval script")


@dataclass
class _QueueTask:
    status: TaskStatus
    task_id: str


class FakeRepository:
    def __init__(self, status: TaskStatus = TaskStatus.QUEUED):
        self.task = _QueueTask(status=status, task_id="run-1")

    def get(self, task_id: str):
        if task_id != self.task.task_id:
            return None
        return self.task


def test_redis_queue_enqueue_is_idempotent_until_ack():
    redis_client = FakeRedis()
    queue = RedisTaskQueue(redis_client)

    queue.enqueue("run-1")
    queue.enqueue("run-1")
    first = queue.claim_next(worker_id="worker-a", lease_seconds=30, block_ms=0)

    assert first is not None
    assert first.run_id == "run-1"
    assert queue.claim_next(worker_id="worker-b", lease_seconds=30, block_ms=0) is None

    queue.ack(first)
    queue.enqueue("run-1")
    second = queue.claim_next(worker_id="worker-b", lease_seconds=30, block_ms=0)

    assert second is not None
    assert second.run_id == "run-1"
    assert second.message_id != first.message_id


def test_redis_queue_reclaims_stale_pending_message():
    redis_client = FakeRedis()
    queue = RedisTaskQueue(redis_client, reclaim_grace_seconds=0)

    queue.enqueue("run-1")
    first = queue.claim_next(worker_id="worker-a", lease_seconds=5, block_ms=0)
    assert first is not None

    redis_client.advance(6000)
    reclaimed = queue.claim_next(worker_id="worker-b", lease_seconds=5, block_ms=0)

    assert reclaimed is not None
    assert reclaimed.run_id == "run-1"
    assert reclaimed.message_id == first.message_id
    assert reclaimed.consumer == "worker-b"


def test_redis_queue_heartbeat_prevents_premature_reclaim():
    redis_client = FakeRedis()
    queue = RedisTaskQueue(redis_client, reclaim_grace_seconds=0)

    queue.enqueue("run-1")
    first = queue.claim_next(worker_id="worker-a", lease_seconds=5, block_ms=0)
    assert first is not None

    redis_client.advance(4000)
    queue.heartbeat(first)
    redis_client.advance(4000)

    assert queue.claim_next(worker_id="worker-b", lease_seconds=5, block_ms=0) is None

    redis_client.advance(2000)
    reclaimed = queue.claim_next(worker_id="worker-b", lease_seconds=5, block_ms=0)

    assert reclaimed is not None
    assert reclaimed.message_id == first.message_id


def test_local_task_queue_swallows_redis_outage_and_leaves_run_queued():
    class BrokenRedis:
        def xgroup_create(self, *args, **kwargs):
            raise redis.exceptions.ConnectionError("redis down")

    repo = FakeRepository()
    queue = LocalTaskQueue(repo, redis_client=BrokenRedis())

    queue.enqueue("run-1")

    assert repo.get("run-1").status == TaskStatus.QUEUED


@pytest.mark.redis
def test_redis_queue_live_roundtrip():
    redis_url = os.getenv("MEDICAL_EVALS_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip(
            "Redis integration unavailable: set MEDICAL_EVALS_TEST_REDIS_URL "
            "to a disposable Redis instance"
        )

    redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    try:
        redis_client.ping()
    except redis.exceptions.RedisError as error:
        pytest.skip(f"Redis integration unavailable: {error}")

    key_prefix = f"medical-evals-test:{uuid4().hex}"
    queue = RedisTaskQueue(
        redis_client,
        stream_key=f"{key_prefix}:stream",
        group_name=f"{key_prefix}:group",
        dedupe_prefix=f"{key_prefix}:dedupe",
        reclaim_grace_seconds=0,
    )

    queue.enqueue("run-1")
    first = queue.claim_next(worker_id="worker-a", lease_seconds=1, block_ms=0)

    assert first is not None
    queue.ack(first)
    queue.enqueue("run-1")
    second = queue.claim_next(worker_id="worker-b", lease_seconds=1, block_ms=0)

    assert second is not None
    assert second.run_id == "run-1"
    queue.ack(second)
