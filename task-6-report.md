# Task 6 Report

Date: 2026-08-27

## Status

Task 6 is implemented, review findings are fixed, and the backend is verified with focused result/security regression coverage plus a clean full backend pytest run.

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
- Made v1 cancel/delete state changes repository-atomic and conditional on allowed source statuses, so terminal runs are not overwritten by late cancel requests and running runs are not deleted by a stale read/then-write path.
- Persisted per-sample results into indexed `evaluation_sample_results` rows during worker execution and changed v1 sample pagination to use PostgreSQL/SQLAlchemy `COUNT + LIMIT/OFFSET` reads instead of scanning `samples.jsonl`.
- Added a compatibility fallback so v1 sample retrieval still pages over `samples.jsonl` when a run has no persisted DB sample rows, covering legacy, migrated, or externally finalized runs without changing ownership checks.
- Scoped the Task 6 common error envelope to `/api/v1/evaluations...` routes so existing `/api/v1/models...` behavior remains unchanged.
- Normalized mixed naive/aware `created_after` / `created_before` filters before comparison and query application to avoid 500s from timezone mismatches.
- Added regression coverage for cancel/retry/delete success and conflict cases, admin visibility, cross-user mutation attempts, repository-atomic state guards, and mixed-timezone date filtering.

## Tests

Focused result/security regression suite:

```bash
UV_CACHE_DIR=/private/tmp/medical-evals-uv-cache uv run pytest \
  tests/test_results_security.py \
  tests/test_result_persistence.py \
  tests/test_reports.py \
  tests/test_catalog_routes.py -q
```

Result: `10 passed`

Full backend suite:

```bash
UV_CACHE_DIR=/private/tmp/medical-evals-uv-cache uv run pytest -q
```

Result: `154 passed, 2 skipped`

## Concerns

- The v1 artifact API and legacy sample fallback still rely on the file-backed artifacts (`report.html`, `run.log`, `summary.json`, `metadata.json`, `samples.jsonl`). Sample pagination now prefers indexed DB rows when present, but artifact indexing itself is still not moved into PostgreSQL.
- Task 7 hardening is still intentionally out of scope here: no SSRF hardening, rate limiting, or deeper production security checks were added in this change.
