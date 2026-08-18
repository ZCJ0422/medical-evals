# Evaluation Metrics and Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate parse success from answer accuracy and restore durable per-sample records and execution logs for Web evaluations.

**Architecture:** Evaluator adapters emit one normalized sample record after each sample. The Worker appends records to a task artifact directory and persists aggregate metrics in SQLite. The results API exposes aggregate metrics and a paginated administrator-only sample endpoint; the frontend renders the distinct metrics and sample diagnostics.

**Tech Stack:** Python, FastAPI, SQLite, Pydantic, React/Next.js, TypeScript, pytest, Playwright.

## Global Constraints

- Preserve existing uncommitted user changes; do not reset or overwrite unrelated files.
- Keep existing `total_score` data readable for historical tasks.
- Raw model output is administrator-only.
- JSONL sample records must be flushed after each completed sample.
- Follow TDD: each behavior starts with a failing test.

---

### Task 1: Add artifact writer and metric model

**Files:**
- Create: `backend/medical_evals_api/artifacts.py`
- Modify: `backend/medical_evals_api/evaluator_adapter.py`
- Test: `backend/tests/test_artifacts.py`
- Test: `backend/tests/test_evaluator_adapter.py`

**Interfaces:**
- `ArtifactWriter(artifact_root: Path, task_id: str)` with `append_sample(record: dict)`, `log(message: str)`, and `write_summary(summary: dict)`.
- `EvaluationRunResult` gains `accuracy`, `parse_success_rate`, `request_success_count`, `parse_failed_count`, and `samples`/sample callback support while preserving existing fields.

- [ ] Write failing tests for JSONL append/flush, summary output, and MedQA parse-success versus accuracy calculations.
- [ ] Run the focused tests and confirm they fail for the missing interfaces/fields.
- [ ] Implement the writer and adapter metric calculations with minimal changes to existing adapter behavior.
- [ ] Run focused tests and confirm they pass.

### Task 2: Persist artifacts and expanded result aggregates in the Worker/repository

**Files:**
- Modify: `backend/medical_evals_api/db.py`
- Modify: `backend/medical_evals_api/repositories/tasks.py`
- Modify: `backend/medical_evals_api/worker.py`
- Modify: `backend/medical_evals_api/config.py`
- Test: `backend/tests/test_result_persistence.py`
- Test: `backend/tests/test_real_worker.py`

**Interfaces:**
- `TaskRepository.save_result(...)` stores independent accuracy/parse fields and remains able to read old rows.
- `Worker.run_task(...)` creates `artifact_dir / task_id`, appends each sample, writes `summary.json`, and logs terminal state.

- [ ] Add failing repository/worker tests for expanded columns, historical-row fallback, and artifact files after a completed run.
- [ ] Run the focused tests and verify the new assertions fail.
- [ ] Add idempotent SQLite columns, repository serialization, and Worker artifact callbacks.
- [ ] Run focused repository/worker tests and confirm they pass.

### Task 3: Update results API and add administrator sample records endpoint

**Files:**
- Modify: `backend/medical_evals_api/services/results.py`
- Modify: `backend/medical_evals_api/routes/results.py`
- Test: `backend/tests/test_results_security.py`
- Test: `backend/tests/test_result_persistence.py`

**Interfaces:**
- Results response exposes `parse_success_rate`, `accuracy`, `request_success_count`, `parse_failed_count`, `failed_count`, and `retry_count`; `total_score` remains a compatibility field.
- `GET /api/evaluations/{task_id}/samples?offset=0&limit=50` returns administrator-only sample records and pagination metadata.

- [ ] Add failing API tests for distinct metric names, legacy fallback, pagination, and authorization.
- [ ] Run focused API tests and confirm the expected failures.
- [ ] Implement service/route models and JSONL pagination without exposing samples through the public aggregate response.
- [ ] Run focused API tests and confirm they pass.

### Task 4: Render corrected metrics and sample diagnostics in the frontend

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/result-summary.tsx`
- Modify: `frontend/lib/i18n.tsx`
- Test: `frontend/e2e/evaluation.spec.ts`

**Interfaces:**
- `ResultSummary` uses nullable `parse_success_rate` and explicit `accuracy`.
- Frontend fetches sample records only for the administrator results view and labels accuracy separately from parse success.

- [ ] Add failing E2E assertions for “Parse success rate” and “Answer accuracy”, and sample diagnostics when artifacts exist.
- [ ] Run the targeted E2E test and verify it fails against the old labels.
- [ ] Update types, API client, translations, cards, and sample table/empty state.
- [ ] Run typecheck, build, and targeted E2E tests.

### Task 5: Update report output and run the full verification suite

**Files:**
- Modify: `backend/medical_evals_api/services/reports.py`
- Modify: `backend/tests/test_reports.py`
- Modify: `README.md` or relevant technical docs if field names are documented.

- [ ] Add a failing report test asserting the distinct metric labels and summary values.
- [ ] Implement report rendering using accuracy and parse success fields.
- [ ] Run all backend tests, frontend typecheck/build, and E2E tests.
- [ ] Inspect `git diff --check` and artifact paths; report any unrelated pre-existing warnings separately.
