# Task 4 Report

## Scope

Implemented Task 4 in `/Users/zhangchj/Documents/project/medical_bench/medical-evals/.worktrees/medical-evals-backend` by migrating the user-facing evaluation catalog and evaluation run persistence path to PostgreSQL-backed SQLAlchemy records for the `v1` API surface.

## Fix Round After `67feffa`

Addressed the Task 4 review findings without adding Redis:

- Added Alembic revision `0002_evaluation_run_leases` for databases already on `0001_initial_workbench`.
  - Adds `evaluation_runs.name`, backfills existing rows as `Evaluation <run_id>`, then makes the column non-null.
  - Adds nullable `lease_owner` and timezone-aware `lease_expires_at` columns plus an expiry index.
  - Changes `init-db` to run `alembic upgrade head` before seeding built-in definitions; it no longer treats `metadata.create_all()` as a schema upgrade.
- Restored durable SQLAlchemy/PostgreSQL worker lease behavior.
  - Claims use `SELECT ... FOR UPDATE SKIP LOCKED`, set owner and expiry, and commit atomically.
  - Renewal requires the current owner and an unexpired running lease.
  - Expired leases are failed and cleared; startup recovery only fails running rows with no lease, preserving live leases owned by other workers.
  - Worker-owned progress, result, and terminal status writes reject stale or wrong owners.
  - A Worker no longer rewrites an already-claimed running row before its first lease renewal.
- Removed the v1 foreign-key hazard from synthetic fixed-admin identity.
  - `/api/v1` authentication resolves a legacy fixed-admin token to the persisted bootstrap admin row.
  - Synthetic compatibility remains limited to legacy admin-only routes backed by the legacy SQLite repository and cannot create v1 PostgreSQL-owned resources.
- Restored all current `/api/v1` auth, catalog, model, and evaluation routes to the generated OpenAPI schema.
- Reworked PostgreSQL verification so SQLite is not represented as PostgreSQL coverage.
  - The live integration test uses an isolated temporary schema in a disposable PostgreSQL database supplied by `MEDICAL_EVALS_TEST_POSTGRES_URL`.
  - It upgrades an existing `0001` schema, verifies the non-null name migration, and exercises PostgreSQL claim, ownership, renewal, and expiry recovery.
  - When the URL is unavailable, the test skips explicitly with: `PostgreSQL integration unavailable: set MEDICAL_EVALS_TEST_POSTGRES_URL to a disposable PostgreSQL database`.
  - A separate SQLite test verifies cross-dialect Alembic upgrade compatibility only; it is not counted as PostgreSQL verification.

## What Changed

- Added built-in evaluation definition metadata for `medqa` and `healthbench`, including split metadata, sample counts, default sample limits, and `requires_judge`.
- Added PostgreSQL-backed evaluation domain models in `backend/medical_evals_api/models/evaluations.py`.
- Added `EvaluationRepository` in `backend/medical_evals_api/repositories/evaluations.py` to:
  - seed built-in evaluation definitions
  - create owned evaluation runs
  - enforce owned model-profile lookup
  - snapshot non-secret model metadata into `run_model_snapshots`
  - list/get owned runs
  - persist run status/progress/results
  - support worker claim and result retrieval
- Added `v1` catalog and evaluation routes:
  - `GET /api/v1/datasets`
  - `GET /api/v1/evaluations`
  - `POST /api/v1/evaluations`
  - `GET /api/v1/evaluations/{run_id}`
  - `POST /api/v1/evaluations/{run_id}/cancel`
  - `POST /api/v1/evaluations/{run_id}/retry`
  - `POST /api/v1/evaluations/{run_id}/resume`
  - `DELETE /api/v1/evaluations/{run_id}`
- Updated worker/queue/CLI/results/report paths so the live `v1` flow can execute against `EvaluationRepository` rather than the legacy SQLite `TaskRepository`.
- Preserved legacy admin-route compatibility where needed by:
  - keeping old `/api/evaluations` routes
  - allowing signed fixed-admin tokens without requiring a DB-backed user row
  - resolving legacy SQLite result/report lookups before attempting the PostgreSQL repository
- Fixed `get_session()` so direct test usage and env-driven SQLite overrides work again.

## Tests Preserved

Preserved the prior implementer’s useful partial tests:

- `backend/tests/test_catalog_routes.py`
- `backend/tests/test_evaluation_persistence_postgres.py`

These became the primary red/green Task 4 tests.

## Verification

Focused Task 4 red-state check:

- `uv run pytest tests/test_catalog_routes.py tests/test_evaluation_persistence_postgres.py -q`
- Initial result: failed as expected because `v1` catalog/evaluation routes were missing.

Focused Task 4 verification:

- `uv run pytest tests/test_catalog_routes.py tests/test_evaluation_persistence_postgres.py -q`
- Result: `4 passed`

Task 4 verification set from the brief:

- `uv run pytest tests/test_catalog_routes.py tests/test_evaluation_persistence_postgres.py tests/test_medqa_core_parity.py tests/test_healthbench_metrics.py -q`
- Result: `11 passed`

Follow-up regression set for touched compatibility paths:

- `uv run pytest tests/test_result_persistence.py tests/test_user_isolation.py tests/test_database_config.py -q`
- Initial result: failed due to legacy admin/auth and session-resolution regressions.
- Final result after fixes: `10 passed`

Final combined verification:

- `uv run pytest tests/test_catalog_routes.py tests/test_evaluation_persistence_postgres.py tests/test_medqa_core_parity.py tests/test_healthbench_metrics.py tests/test_result_persistence.py tests/test_user_isolation.py tests/test_database_config.py tests/test_auth.py -q`
- Result: `30 passed`

Fix-round focused migration/catalog/identity/lease verification:

- `uv run pytest tests/test_database_config.py tests/test_catalog_routes.py tests/test_evaluation_persistence_postgres.py -q`
- Result: `12 passed, 1 skipped`

Fix-round legacy compatibility verification after scoping synthetic identity to legacy admin routes:

- `uv run pytest tests/test_result_persistence.py tests/test_evaluation_persistence_postgres.py tests/test_user_isolation.py tests/test_auth.py -q`
- Result: `20 passed, 1 skipped`

Final fix-round regression verification:

- `uv run pytest tests/test_catalog_routes.py tests/test_evaluation_persistence_postgres.py tests/test_database_config.py tests/test_medqa_core_parity.py tests/test_healthbench_metrics.py tests/test_result_persistence.py tests/test_user_isolation.py tests/test_auth.py tests/test_repositories.py tests/test_worker.py tests/test_model_profiles.py tests/test_model_security.py -q`
- Result: `62 passed, 1 skipped in 11.95s`
- Skip: the live PostgreSQL integration test was not run because `MEDICAL_EVALS_TEST_POSTGRES_URL` was not configured. No SQLite result is being used as PostgreSQL verification.

## Files Changed

- `backend/medical_evals_api/auth.py`
- `backend/medical_evals_api/cli.py`
- `backend/medical_evals_api/database.py`
- `backend/medical_evals_api/evaluation_sources.py`
- `backend/medical_evals_api/main.py`
- `backend/medical_evals_api/models/__init__.py`
- `backend/medical_evals_api/models/evaluations.py`
- `backend/medical_evals_api/queue.py`
- `backend/medical_evals_api/repositories/evaluations.py`
- `backend/medical_evals_api/routes/catalog.py`
- `backend/medical_evals_api/routes/evaluations.py`
- `backend/medical_evals_api/routes/reports.py`
- `backend/medical_evals_api/routes/results.py`
- `backend/medical_evals_api/schemas/evaluations.py`
- `backend/medical_evals_api/services/results.py`
- `backend/medical_evals_api/worker.py`
- `backend/tests/test_catalog_routes.py`
- `backend/tests/test_evaluation_persistence_postgres.py`

## Concerns / Follow-Ups

- The legacy SQLite `TaskRepository` still exists for older admin routes and tests, but the live `v1` evaluation creation and worker execution path now uses `EvaluationRepository`.
- The enqueue seam for Task 5 is currently `LocalTaskQueue(repo).enqueue(run_id)` after repository creation/commit. There is no Redis queue yet.
- `run_model_snapshots` intentionally stores only non-secret snapshot fields in this task; worker secret resolution still reads encrypted credentials from the source model profiles.
- Live PostgreSQL execution remains environment-blocked until a disposable database URL is supplied through `MEDICAL_EVALS_TEST_POSTGRES_URL`; the integration path is present and skips clearly when unavailable.
