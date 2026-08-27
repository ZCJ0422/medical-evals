# Task 6 Report

Date: 2026-08-27

## Status

Task 6 is implemented in the current worktree and verified with focused v1 route/result coverage plus adjacent compatibility checks.

## Implemented

- Added versioned `/api/v1/evaluations` create, list, detail, cancel, retry, and delete routes.
- Added `/api/v1/evaluations/{run_id}/summary`, `/samples`, `/artifacts`, and artifact download routes.
- Added the common v1 error envelope:
  - `{ "error": { "code": str, "message": str, "request_id": str } }`
- Added per-request `X-Request-ID` generation and propagation.
- Enforced user/admin ownership checks on v1 evaluation, result, and artifact access.
- Reused `EvaluationRepository` and the existing Redis enqueue seam instead of duplicating evaluation logic.
- Removed the stale v1 `resume` route while preserving the legacy `/api/evaluations/{task_id}/resume` compatibility path.
- Extended repository list filtering for v1 status/date/pagination support.
- Added focused Task 6 tests and updated explicitly needed compatibility tests to use temp SQLite wiring and the new v1 error contract.

## Tests

Focused Task 6 suite:

```bash
UV_CACHE_DIR=/private/tmp/medical-evals-uv-cache uv run pytest \
  tests/test_v1_evaluation_routes.py \
  tests/test_results_security.py \
  tests/test_result_persistence.py \
  tests/test_reports.py \
  tests/test_catalog_routes.py -q
```

Result: `14 passed`

Adjacent compatibility slice:

```bash
UV_CACHE_DIR=/private/tmp/medical-evals-uv-cache uv run pytest \
  tests/test_evaluation_persistence_postgres.py \
  tests/test_evaluation_routes.py \
  tests/test_delete_route.py \
  tests/test_evaluation_list.py -q
```

Result: `21 passed, 1 skipped`

## Concerns

- The v1 artifact API currently exposes the existing file-backed artifacts (`report.html`, `run.log`, `summary.json`, `metadata.json`, `samples.jsonl`) through authenticated ownership-checked routes. It does not yet move artifact indexing fully into PostgreSQL; that remains acceptable for Task 6 given the existing worker persistence model.
- Task 7 hardening is still intentionally out of scope here: no SSRF hardening, rate limiting, or deeper production security checks were added in this change.
