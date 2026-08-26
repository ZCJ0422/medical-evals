# Task 5 Report

Date: 2026-08-26

## Scope

Implemented Task 5 for the backend worktree:

- Replaced the no-op local enqueue path with a Redis-backed queue implementation using Redis Streams consumer groups.
- Added idempotent enqueue by `run_id`.
- Added queue claim metadata, queue heartbeat, terminal ack, and queued-run reconciliation.
- Added repository support for claiming a specific queued run and listing queued run ids for recovery.
- Moved the worker loop into `Worker.run_forever()` and wired the CLI worker command through Redis + PostgreSQL recovery.
- Added focused queue and worker tests, including a live Redis integration test with explicit skip behavior when `MEDICAL_EVALS_TEST_REDIS_URL` is unavailable.

## Design Notes

- PostgreSQL remains the source of truth for task status, progress, results, and lease state.
- Redis only carries delivery state. Queue ack happens only after the worker has reached a durable terminal state in PostgreSQL.
- Route-side enqueue failures caused by Redis outages are swallowed intentionally so runs remain visible and recoverable as `queued`.
- Worker startup and idle reconciliation re-enqueue queued PostgreSQL runs into Redis so a Redis outage does not orphan durable queued work.

## Files Changed

- `backend/medical_evals_api/queue.py`
- `backend/medical_evals_api/redis_queue.py`
- `backend/medical_evals_api/worker.py`
- `backend/medical_evals_api/cli.py`
- `backend/medical_evals_api/repositories/evaluations.py`
- `backend/tests/test_redis_queue.py`
- `backend/tests/test_worker.py`
- `backend/tests/test_real_worker.py`
- `backend/pyproject.toml`

## Test Results

Command run:

```bash
uv run pytest tests/test_redis_queue.py tests/test_worker.py tests/test_real_worker.py tests/test_medqa_core_parity.py tests/test_healthbench_real_worker.py -q
```

Result:

- `39 passed`
- `1 skipped`

Skip detail:

- The live Redis integration test is skipped when `MEDICAL_EVALS_TEST_REDIS_URL` is not configured or Redis is unreachable.

## Remaining Concerns

- The live Redis integration path was not exercised in this environment because `MEDICAL_EVALS_TEST_REDIS_URL` was not provided.
- The queue implementation uses Redis Streams plus PostgreSQL reconciliation rather than introducing additional Redis-side state beyond stream pending entries and `run_id` dedupe keys. This keeps recovery simple, but production behavior should still be observed under real worker crash/restart scenarios.
