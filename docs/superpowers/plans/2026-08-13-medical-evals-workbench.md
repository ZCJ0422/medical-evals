# Medical Evals Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an internal single-admin Medical Evals workbench with a separated web frontend, HTTP API, local SQLite/file persistence, asynchronous evaluation workers, protected benchmark content, and per-run HTML/PDF reports.

**Architecture:** Add a `backend/` service that owns authentication, task orchestration, storage, report generation, and protected data access. Add a separate `frontend/` application that communicates only through the API. A local worker process consumes persisted queued tasks and invokes the existing `medical-evals` evaluator through an adapter boundary; SQLite stores task metadata and JSON/JSONL files store detailed run artifacts.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLite, pytest; existing `medical-evals` CompletionFn/Evals runtime; Next.js/React, TypeScript, Tailwind CSS, shadcn/ui, Playwright; HTML report templates plus a local PDF renderer selected behind a report interface.

## Global Constraints

- First release uses one fixed test account and one administrator role; no public registration, invitations, SSO, or LDAP.
- One evaluation run evaluates exactly one target model; a separate Judge Model is recorded and used for scoring.
- Only platform-provided dataset versions and platform-provided Rubrics are supported; users cannot upload datasets or author Rubrics.
- Benchmark questions, answers, and complete Rubrics must not appear in ordinary result responses, URLs, localStorage, or frontend build artifacts.
- Administrator-only raw-sample access must use a separate protected API route; audit logging is deferred.
- Tasks run asynchronously and persist across page reloads; the frontend polls progress and does not show per-sample live logs.
- Transient timeout, rate-limit, and provider errors retry up to three times with increasing delay; authentication, parameter, and data-format errors do not retry.
- Results and local artifacts are retained indefinitely; only the administrator can permanently delete completed or failed tasks after confirmation.
- A running task must be cancelled before deletion; deletion removes task metadata, result files, run artifacts, and reports.
- Reports are per-task HTML/PDF artifacts; the administrator may view, generate, and download them.
- Preserve existing uncommitted changes in `medical_evals/evals/healthbench.py`, `registry/evals/medical_healthbench.yaml`, `tests/medical_evals/test_healthbench_eval.py`, and `dataset/`.

---

## File Map

Create the following focused boundaries:

- `backend/medical_evals_api/` — FastAPI application, auth, domain schemas, repositories, task queue, worker, and report services.
- `backend/tests/` — API, repository, worker, security, and report tests using fake providers and temporary directories.
- `frontend/` — Next.js application, shared UI primitives, task flows, result views, and Playwright tests.
- `frontend/e2e/` — browser-level authentication, task creation, progress, result, and protected-content tests.
- `backend/data/` — runtime-only SQLite and artifacts; add to `.gitignore`, never commit generated results or credentials.
- `docs/superpowers/plans/` — this plan and future implementation plans.
- `docs/project-technical.md` and `README.md` — update only after the vertical slice is runnable.

The existing evaluator remains under `medical_evals/`, and the new backend must call it through an adapter rather than embedding long-running evaluation work in request handlers.

## Task 1: Establish backend/frontend project boundaries and shared contracts

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/medical_evals_api/__init__.py`
- Create: `backend/medical_evals_api/main.py`
- Create: `backend/medical_evals_api/config.py`
- Create: `backend/medical_evals_api/schemas/common.py`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/app/page.tsx`
- Create: `frontend/app/globals.css`
- Create: `backend/tests/test_health.py`
- Create: `frontend/tests/smoke.spec.ts`
- Modify: `.gitignore`

**Interfaces:**
- Produce `GET /healthz -> {"status":"ok"}`.
- Produce shared task enums and schemas: `TaskStatus`, `TaskSummary`, `TaskProgress`, `ProviderSummary`, `ModelSummary`, `DatasetVersionSummary`, and `RubricSummary`.
- Frontend consumes the API base URL from `NEXT_PUBLIC_API_BASE_URL` and renders a temporary health-aware shell.

- [ ] **Step 1: Add backend dependency and test configuration.**

Define a backend package with FastAPI, Uvicorn, Pydantic Settings, and pytest dependencies. Configure pytest to run from `backend/` and use Python 3.10-compatible typing.

- [ ] **Step 2: Write the failing health endpoint test.**

```python
from fastapi.testclient import TestClient

from medical_evals_api.main import app


def test_healthz_returns_ok():
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

Run: `cd backend && pytest -q tests/test_health.py`
Expected: FAIL because `app` and `/healthz` do not exist.

- [ ] **Step 3: Implement the health endpoint and typed configuration.**

Create `Settings` with `database_path`, `artifact_dir`, `fixed_admin_username`, `fixed_admin_password_hash`, and `frontend_origin`. Make the application constructible without network calls or real provider credentials.

- [ ] **Step 4: Scaffold the frontend shell and smoke test.**

Render an accessible “Medical Evals” shell with a loading/empty state. Add a Playwright smoke test that opens `/` and asserts the application title and shell heading.

- [ ] **Step 5: Add runtime paths to `.gitignore` and run both checks.**

Run: `cd backend && pytest -q` and `cd frontend && npm run test:e2e -- tests/smoke.spec.ts`.
Expected: both pass; no runtime database, credentials, or result artifacts are tracked.

- [ ] **Step 6: Commit the boundary.**

```bash
git add backend frontend .gitignore
git commit -m "feat: scaffold medical evals workbench services"
```

## Task 2: Implement fixed-admin authentication and API authorization

**Files:**
- Create: `backend/medical_evals_api/auth.py`
- Create: `backend/medical_evals_api/routes/auth.py`
- Create: `backend/medical_evals_api/routes/me.py`
- Create: `backend/tests/test_auth.py`
- Modify: `backend/medical_evals_api/main.py`
- Modify: `backend/medical_evals_api/config.py`
- Modify: `frontend/app/page.tsx`
- Create: `frontend/app/login/page.tsx`
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/auth.ts`
- Create: `frontend/e2e/auth.spec.ts`

**Interfaces:**
- `POST /api/auth/login` accepts `{username, password}` and returns `{access_token, user:{username, role:"admin"}}`.
- `GET /api/me` requires a bearer token and returns the administrator identity.
- `require_admin(request) -> AdminIdentity` is the single backend authorization dependency.
- Frontend stores only the short-lived access token in memory or an HttpOnly cookie strategy chosen by the backend; never store provider API keys in browser storage.

- [ ] **Step 1: Write authentication tests for success, failure, and protected routes.**

Cover valid fixed credentials, invalid credentials returning 401, missing token returning 401, and a valid token returning the admin identity. Use a test settings override; do not use a production password.

- [ ] **Step 2: Implement password verification and signed session tokens.**

Hash the configured test password with a standard password hashing library and sign a short-lived token with a local secret. Make token expiry and secret configurable. Keep authentication isolated from evaluation code.

- [ ] **Step 3: Add login and identity routes.**

Return generic invalid-credential errors, avoid revealing whether the username exists, and set no-cache headers on authentication responses.

- [ ] **Step 4: Add the frontend login flow.**

Create labeled username/password fields, loading state, invalid-credential state, and redirect to `/app` after login. Add an authenticated API client that handles 401 by returning the user to `/login`.

- [ ] **Step 5: Run tests and commit.**

Run: `cd backend && pytest -q tests/test_auth.py`; `cd frontend && npm run test:e2e -- e2e/auth.spec.ts`.

```bash
git add backend frontend
git commit -m "feat: add fixed administrator authentication"
```

## Task 3: Add SQLite repositories and immutable evaluation configuration snapshots

**Files:**
- Create: `backend/medical_evals_api/db.py`
- Create: `backend/medical_evals_api/models.py`
- Create: `backend/medical_evals_api/repositories/tasks.py`
- Create: `backend/medical_evals_api/repositories/catalog.py`
- Create: `backend/medical_evals_api/catalog/seed.py`
- Create: `backend/tests/test_repositories.py`
- Modify: `backend/medical_evals_api/config.py`

**Interfaces:**
- `TaskRepository.create(spec: EvaluationTaskCreate) -> EvaluationTask`
- `TaskRepository.get(task_id: str) -> EvaluationTask | None`
- `TaskRepository.list(filters: TaskFilters) -> list[EvaluationTask]`
- `TaskRepository.update_progress(task_id: str, progress: TaskProgress) -> EvaluationTask`
- `TaskRepository.set_status(task_id: str, status: TaskStatus, error: str | None = None) -> EvaluationTask`
- `TaskRepository.delete(task_id: str) -> None`
- `CatalogRepository.list_models()`, `list_judges()`, `list_dataset_versions()`, and `list_rubrics()` return only safe summaries.

- [ ] **Step 1: Define database schema and repository tests.**

Test that task creation stores a generated ID, immutable target/Judge/provider/dataset/Rubric snapshots, timestamps, status `queued`, and zeroed progress. Test that updates never mutate the original configuration snapshot.

- [ ] **Step 2: Implement SQLite initialization and migrations.**

Create tables for `tasks`, `task_progress`, `task_artifacts`, and catalog entries. Use parameterized SQL or a small repository layer; do not expose database connections to route handlers.

- [ ] **Step 3: Seed safe platform catalog metadata.**

Represent provider/model identifiers, dataset IDs and versions, and Rubric IDs/versions without embedding benchmark questions or answers in API-safe catalog records.

- [ ] **Step 4: Implement deletion semantics.**

Allow deletion only for `completed`, `partial_failed`, `failed`, or `cancelled`; reject deletion for `queued` and `running`. Return a typed conflict error rather than silently deleting active work.

- [ ] **Step 5: Run repository tests and commit.**

Run: `cd backend && pytest -q tests/test_repositories.py`.

```bash
git add backend
git commit -m "feat: add sqlite task and catalog repositories"
```

## Task 4: Implement catalog, preflight, task creation, progress, and cancellation APIs

**Files:**
- Create: `backend/medical_evals_api/routes/catalog.py`
- Create: `backend/medical_evals_api/routes/evaluations.py`
- Create: `backend/medical_evals_api/services/preflight.py`
- Create: `backend/tests/test_evaluation_routes.py`
- Modify: `backend/medical_evals_api/main.py`

**Interfaces:**
- `GET /api/providers`
- `GET /api/models`
- `GET /api/judges`
- `GET /api/datasets`
- `GET /api/datasets/{dataset_id}/versions`
- `GET /api/rubrics`
- `POST /api/evaluations/preflight`
- `POST /api/evaluations`
- `GET /api/evaluations`
- `GET /api/evaluations/{id}`
- `GET /api/evaluations/{id}/progress`
- `POST /api/evaluations/{id}/cancel`

- [ ] **Step 1: Write route tests for one-model task creation and safe responses.**

Assert that a valid request creates one `queued` task; a request with multiple target models is rejected; catalog and result-facing responses contain IDs and metadata but no question, answer, or complete Rubric fields.

- [ ] **Step 2: Implement catalog routes with administrator authentication.**

Return deterministic catalog data and dataset version metadata. Never return the raw dataset file through these routes.

- [ ] **Step 3: Implement preflight validation.**

Validate model and Judge IDs, dataset/Rubric compatibility, parameter ranges, endpoint readiness, and local queue acceptance. Return structured errors with field paths and a cost/token estimate when metadata permits it.

- [ ] **Step 4: Implement task creation and status routes.**

Create a task only after successful preflight, persist the configuration snapshot, and return a task ID without waiting for evaluation execution.

- [ ] **Step 5: Implement cancellation with a cooperative cancellation flag.**

Set a persisted cancellation request that the Worker checks between samples and before retrying. A cancelled task must not be reported as completed.

- [ ] **Step 6: Run route tests and commit.**

Run: `cd backend && pytest -q tests/test_evaluation_routes.py`.

```bash
git add backend
git commit -m "feat: add evaluation task api"
```

## Task 5: Build the local queue, Worker, retry policy, and evaluator adapter

**Files:**
- Create: `backend/medical_evals_api/queue.py`
- Create: `backend/medical_evals_api/worker.py`
- Create: `backend/medical_evals_api/evaluator_adapter.py`
- Create: `backend/medical_evals_api/retry.py`
- Create: `backend/tests/test_worker.py`
- Modify: `backend/medical_evals_api/services/preflight.py`

**Interfaces:**
- `LocalTaskQueue.enqueue(task_id: str) -> None`
- `LocalTaskQueue.claim_next() -> str | None`
- `EvaluationAdapter.run(task: EvaluationTask, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult`
- `RetryPolicy.should_retry(error: ProviderError, attempt: int) -> bool`
- `Worker.run_once() -> None`

- [ ] **Step 1: Write fake-adapter tests for state transitions.**

Cover queued → running → completed, partial failures, task-level failures, cancellation between samples, and page-independent progress persistence. Use a fake adapter that returns deterministic samples without reading real benchmark content.

- [ ] **Step 2: Implement the persisted local queue.**

Use SQLite task state as the queue source so a process restart can recover queued work. Claim work transactionally and prevent two local Worker loops from claiming the same task.

- [ ] **Step 3: Implement the adapter boundary to existing medical-evals code.**

Translate the immutable task snapshot into the existing CompletionFn/Evals invocation. Keep provider credentials in backend configuration, pass only the selected model and parameters, and write detailed JSONL artifacts under the task artifact directory.

- [ ] **Step 4: Implement retries and progress updates.**

Retry only timeouts, rate limits, and temporary provider failures up to three attempts with increasing delay. Update completed, success, failure, and retry counts after each sample; do not emit per-sample logs through the API.

- [ ] **Step 5: Implement Worker startup and recovery.**

On startup, recover stale `running` tasks as failed with a recoverable error or requeue them only when the persisted task has no completed sample ambiguity. Keep the first implementation conservative: mark interrupted runs `failed` and require a new task.

- [ ] **Step 6: Run worker tests and commit.**

Run: `cd backend && pytest -q tests/test_worker.py`.

```bash
git add backend
git commit -m "feat: add local evaluation worker"
```

## Task 6: Add result aggregation, protected sample access, and report generation

**Files:**
- Create: `backend/medical_evals_api/services/results.py`
- Create: `backend/medical_evals_api/services/reports.py`
- Create: `backend/medical_evals_api/routes/results.py`
- Create: `backend/medical_evals_api/routes/reports.py`
- Create: `backend/medical_evals_api/templates/report.html.j2`
- Create: `backend/tests/test_results_security.py`
- Create: `backend/tests/test_reports.py`
- Modify: `backend/medical_evals_api/main.py`

**Interfaces:**
- `GET /api/evaluations/{id}/results`
- `GET /api/evaluations/{id}/report`
- `POST /api/evaluations/{id}/report/generate`
- `GET /api/evaluations/{id}/samples/{sample_id}` — administrator-only protected route
- `ResultService.get_public_summary(task_id: str) -> EvaluationSummary`
- `ResultService.get_admin_sample(task_id: str, sample_id: str) -> ProtectedSample`
- `ReportService.generate(task_id: str, format: Literal["html", "pdf"]) -> ReportArtifact`

- [ ] **Step 1: Write security tests before exposing results.**

Assert that public summary responses never contain raw question, standard answer, full Rubric, or provider secrets. Assert that the administrator sample route requires authentication and that sample IDs cannot escape the task artifact directory.

- [ ] **Step 2: Implement aggregation from JSONL artifacts.**

Return total score, dimension scores, pass rate, safety metrics, latency, token/cost estimates, success/failure/retry counts, and error categories. Keep raw sample records behind the protected service only.

- [ ] **Step 3: Implement HTML report generation.**

Render a single-task report from the same safe summary schema. Include model/Judge, dataset/Rubric versions, metrics, run metadata, and error summaries; omit raw questions and answers unless a separately authorized administrator-only sample view is used.

- [ ] **Step 4: Implement PDF rendering behind an interface.**

Use the environment’s available local renderer and provide a clear typed error when PDF conversion is unavailable. Store HTML/PDF artifacts under the task directory and record their paths in SQLite.

- [ ] **Step 5: Implement report permissions and permanent deletion cleanup.**

Allow the administrator to generate, view, download, and delete reports only through task ownership checks and artifact path validation. Delete all related files when the task repository deletion succeeds.

- [ ] **Step 6: Run result/report tests and commit.**

Run: `cd backend && pytest -q tests/test_results_security.py tests/test_reports.py`.

```bash
git add backend
git commit -m "feat: add protected results and reports"
```

## Task 7: Build the frontend admin workbench shell and task list

**Files:**
- Create: `frontend/app/app/layout.tsx`
- Create: `frontend/app/app/page.tsx`
- Create: `frontend/app/app/evaluations/page.tsx`
- Create: `frontend/components/layout/sidebar.tsx`
- Create: `frontend/components/evaluations/task-table.tsx`
- Create: `frontend/components/evaluations/status-badge.tsx`
- Create: `frontend/components/ui/` shadcn/ui primitives used by these pages
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/queries.ts`
- Create: `frontend/e2e/task-list.spec.ts`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Consume the typed API methods from `frontend/lib/api.ts`.
- Render task summaries without assuming raw sample fields exist.
- Use the design system direction: professional medical evaluation console, high information clarity, restrained color, visible focus, no decorative gradients as the primary hierarchy.

- [ ] **Step 1: Add frontend API and domain types.**

Define TypeScript types matching backend `TaskStatus`, `TaskSummary`, `TaskProgress`, catalog summaries, and result summaries. Keep API mapping in one module instead of scattering fetch calls across components.

- [ ] **Step 2: Build authenticated layout and navigation.**

Create sidebar/header navigation for Dashboard, Evaluations, Reports, and Admin Catalog. Add loading, unauthorized, and empty states.

- [ ] **Step 3: Build the task table.**

Show task name, target model, Judge Model, dataset version, status, progress, created time, and completion time. Add status filters and a clear “New evaluation” action.

- [ ] **Step 4: Add task-list browser tests.**

Mock only the API boundary in Playwright. Verify login, task list rendering, empty state, status filtering, and that no raw benchmark content is present in the document.

- [ ] **Step 5: Run frontend lint/typecheck/browser tests and commit.**

Run: `cd frontend && npm run lint && npm run typecheck && npm run test:e2e -- e2e/task-list.spec.ts`.

```bash
git add frontend
git commit -m "feat: add admin evaluation workbench shell"
```

## Task 8: Build the create-evaluation flow and progress page

**Files:**
- Create: `frontend/app/app/evaluations/new/page.tsx`
- Create: `frontend/app/app/evaluations/[id]/page.tsx`
- Create: `frontend/components/evaluations/configuration-form.tsx`
- Create: `frontend/components/evaluations/preflight-panel.tsx`
- Create: `frontend/components/evaluations/progress-card.tsx`
- Create: `frontend/components/evaluations/error-summary.tsx`
- Create: `frontend/lib/validation.ts`
- Create: `frontend/e2e/create-evaluation.spec.ts`

**Interfaces:**
- Create request contains one `target_model_id`, one `judge_model_id`, one `dataset_version_id`, one `rubric_id`, generation parameters, concurrency, timeout, and retry policy.
- Preflight returns field errors, warnings, estimated tokens/cost, and `ready: boolean`.
- Progress polling uses `GET /api/evaluations/{id}/progress` and stops on terminal states.

- [ ] **Step 1: Write form validation tests.**

Reject missing target/Judge/dataset selections, invalid temperature/max_tokens/concurrency/timeout values, and any payload containing multiple target models.

- [ ] **Step 2: Build the configuration form.**

Use labeled selects, numeric controls, helper text, and explicit dataset/Rubric version display. Never render dataset question content. Keep a clear distinction between target model and Judge Model.

- [ ] **Step 3: Add preflight and launch behavior.**

Submit preflight first, display blocking errors and estimates, then enable launch only when `ready`. On launch, redirect to the task detail route using the returned task ID.

- [ ] **Step 4: Build progress polling.**

Poll with a bounded interval, show completed/total, percentage, status, success/failure/retry counts, and cancel action. Stop polling on `completed`, `partial_failed`, `failed`, or `cancelled`.

- [ ] **Step 5: Add browser tests and commit.**

Run: `cd frontend && npm run test:e2e -- e2e/create-evaluation.spec.ts`.

```bash
git add frontend
git commit -m "feat: add evaluation creation and progress flow"
```

## Task 9: Build result, protected sample, and report UI

**Files:**
- Create: `frontend/app/app/evaluations/[id]/results/page.tsx`
- Create: `frontend/components/results/summary-cards.tsx`
- Create: `frontend/components/results/error-breakdown.tsx`
- Create: `frontend/components/results/metric-chart.tsx`
- Create: `frontend/components/results/admin-sample-drawer.tsx`
- Create: `frontend/components/reports/report-actions.tsx`
- Create: `frontend/e2e/results-security.spec.ts`

**Interfaces:**
- Public result view consumes only `EvaluationSummary`.
- Administrator sample drawer calls the separate protected sample endpoint and requires explicit user action.
- Report actions call generate/view/download endpoints and show unavailable/failed states.

- [ ] **Step 1: Write browser security tests.**

Assert the result page renders metrics and error categories but not question, answer, or full Rubric fields. Assert sample content appears only after the administrator sample request succeeds.

- [ ] **Step 2: Implement the summary view.**

Show total score, dimension scores, pass rate, safety metrics, latency, tokens, cost, completion counts, and retry/failure counts. Use accessible charts or tables with text equivalents.

- [ ] **Step 3: Implement error breakdown and empty/error states.**

Distinguish no-result, partial-failure, failed-task, and report-generation states. Avoid exposing per-sample details in error summaries.

- [ ] **Step 4: Implement administrator sample drawer.**

Require an explicit “View protected sample” action. Display the sample ID, question, answer, standard answer, and Rubric only after the protected API response; do not preload or cache it in global state.

- [ ] **Step 5: Implement report actions.**

Support generate, view HTML, and download PDF for completed tasks. Show report metadata and failures without silently retrying report generation.

- [ ] **Step 6: Run browser security tests and commit.**

Run: `cd frontend && npm run test:e2e -- e2e/results-security.spec.ts`.

```bash
git add frontend
git commit -m "feat: add evaluation results and reports"
```

## Task 10: Integrate the real worker, add deployment commands, and document the vertical slice

**Files:**
- Create: `backend/medical_evals_api/cli.py`
- Create: `backend/scripts/run_api.sh`
- Create: `backend/scripts/run_worker.sh`
- Create: `backend/tests/test_integration_smoke.py`
- Modify: `backend/medical_evals_api/main.py`
- Modify: `README.md`
- Modify: `docs/project-technical.md`
- Modify: `.gitignore`

**Interfaces:**
- `python -m medical_evals_api.cli api` starts the API.
- `python -m medical_evals_api.cli worker` starts the local Worker loop.
- `python -m medical_evals_api.cli init-db` initializes SQLite and safe catalog metadata.

- [ ] **Step 1: Write an integration smoke test with a fake model provider.**

Create a temporary SQLite/artifact directory, initialize the app, log in, create a one-sample task, run `Worker.run_once()`, query progress/results, and generate an HTML report. Assert no real network or credentials are used.

- [ ] **Step 2: Add API and Worker CLI entry points.**

Make API and Worker separate processes. Ensure startup does not execute a benchmark until a queued task is claimed.

- [ ] **Step 3: Connect the real evaluator adapter behind a feature flag.**

The default development/test mode uses the fake adapter; an explicit configuration selects the existing `medical-evals` adapter and requires provider credentials. Never log credentials.

- [ ] **Step 4: Document local development and security boundaries.**

Document installation, fixed test account configuration, API/Worker commands, frontend environment variables, artifact paths, protected sample behavior, deletion semantics, and the distinction between fake and real evaluation mode.

- [ ] **Step 5: Run the complete verification suite.**

Run:

```bash
cd backend && pytest -q
cd ../frontend && npm run lint && npm run typecheck && npm run test:e2e
```

Expected: backend unit/integration tests, frontend lint/typecheck, and browser tests pass without real provider credentials.

- [ ] **Step 6: Commit the runnable vertical slice.**

```bash
git add backend frontend README.md docs/project-technical.md .gitignore
git commit -m "feat: deliver medical evals workbench vertical slice"
```

## Self-Review Checklist

- [x] Spec coverage: auth, admin-only permissions, one target model, independent Judge Model, platform datasets/Rubrics, preflight, async task state, progress polling, retry policy, local persistence, reports, protected samples, deletion, frontend screens, and tests all have explicit tasks.
- [x] Placeholder scan: no `TODO`, `TBD`, vague “implement later”, or untyped neighboring interfaces are used as implementation instructions.
- [x] Type consistency: task and progress field names are shared between backend schemas, frontend types, repository methods, and route contracts.
- [x] Existing changes are preserved and excluded from the plan’s first commits unless a task explicitly touches the documented integration boundary.

Plan complete and saved to `docs/superpowers/plans/2026-08-13-medical-evals-workbench.md`.

