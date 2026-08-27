# Task 5 Report

Date: 2026-08-26

## Scope

Implemented Task 5 for the backend worktree:

- Replaced the no-op local enqueue path with a Redis-backed queue implementation using Redis Streams consumer groups.
- Added idempotent enqueue by `run_id`.
- Added queue claim metadata, queue heartbeat, terminal ack, and queued-run reconciliation.
- Added repository support for claiming a specific queued run and listing queued run ids for recovery.
- Updated expired lease recovery so leased `running` runs are reset to `queued` and returned for Redis re-enqueue, preserving checkpoints for resume instead of marking them failed.
- Tightened expired lease recovery to a single conditional transition that returns only rows actually reset, preventing a renewed lease from being requeued after candidate selection.
- Moved the worker loop into `Worker.run_forever()` and wired the CLI worker command through Redis + PostgreSQL recovery.
- Added focused queue and worker tests, including a live Redis integration test with explicit skip behavior when `MEDICAL_EVALS_TEST_REDIS_URL` is unavailable.

## Design Notes

- PostgreSQL remains the source of truth for task status, progress, results, and lease state.
- Redis only carries delivery state. Queue ack happens only after the worker has reached a durable terminal state in PostgreSQL.
- Route-side enqueue failures caused by Redis outages are swallowed intentionally so runs remain visible and recoverable as `queued`.
- Worker startup and idle reconciliation re-enqueue queued PostgreSQL runs into Redis so a Redis outage does not orphan durable queued work.
- Expired worker leases are treated as recoverable dispatch failures: the run returns to `queued`, lease fields are cleared, and the worker re-enqueues the recovered `run_id` through Redis Streams.
- Lease recovery is atomic at update time: only rows still `running` with expired leases are reset and returned, closing the renewal-versus-recovery race.

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

Latest command run:

```bash
uv run pytest tests/test_redis_queue.py tests/test_worker.py tests/test_real_worker.py tests/test_evaluation_persistence_postgres.py -q
```

Result:

- `33 passed`
- `2 skipped`

Skip detail:

- The live Redis integration test is skipped when `MEDICAL_EVALS_TEST_REDIS_URL` is not configured or Redis is unreachable.
- The PostgreSQL integration test is skipped when `MEDICAL_EVALS_TEST_POSTGRES_URL` is not configured.

## Remaining Concerns

- The live Redis integration path was not exercised in this environment because `MEDICAL_EVALS_TEST_REDIS_URL` was not provided.
- The live PostgreSQL integration path was not exercised in this environment because `MEDICAL_EVALS_TEST_POSTGRES_URL` was not provided.
- The queue implementation uses Redis Streams plus PostgreSQL reconciliation rather than introducing additional Redis-side state beyond stream pending entries and `run_id` dedupe keys. This keeps recovery simple, but production behavior should still be observed under real worker crash/restart scenarios.
