# SDD ledger — plan: docs/superpowers/plans/2026-08-26-medical-evals-backend.md

## Setup

- Workspace: `/Users/zhangchj/Documents/project/medical_bench/medical-evals/.worktrees/medical-evals-backend`
- Branch: `feature/medical-evals-backend`
- Base commit: `1cde3be`
- Baseline command: `/Users/zhangchj/Documents/project/medical_bench/medical-evals/.venv/bin/pytest -q`
- Baseline result: 176 passed, 20 failed. Existing failures are concentrated in current Worker/core parity tests and predate this plan; they include missing `EvaluationSummary.telemetry` and current real-worker failures.
- Network note: `uv run pytest -q` could not download dependencies because DNS/network access is unavailable; the existing main-repository virtualenv was used for the baseline.

## Plan scan

| Scope | Pair/task | Shared interface or file | Finding | Ruling |
|---|---|---|---|---|
| Pair | Task 1 → Task 2 | SQLAlchemy session factory, users migration | Task 1 creates the session/migration foundation; Task 2 consumes it for users. No contradiction. | Proceed in order. |
| Pair | Task 1 → Task 4 | Database engine, migrations, repository boundary | Task 4 creates evaluation tables in the initial schema and consumes the session factory. No contradiction. | Keep schema creation in Task 1 and repository code in Task 4. |
| Pair | Task 1 → Task 5 | PostgreSQL state and Redis client | Task 5 consumes both factories and replaces only the queue implementation. No contradiction. | PostgreSQL remains source of truth. |
| Pair | Task 2 → Task 3 | `CurrentUser`, ownership filtering | Task 3 consumes the user dependency and adds user-owned model profiles. No contradiction. | Require user ownership in every model route. |
| Pair | Task 2 → Task 6 | Auth dependency and `/api/v1` routes | Task 6 consumes `require_user`/`require_admin`. No contradiction. | Remove fixed identity dependencies from v1 routes. |
| Pair | Task 3 → Task 4 | Model profile IDs and run snapshots | Task 4 consumes model profile ownership and resolves metadata into snapshots. No contradiction. | Never copy plaintext secrets into snapshots. |
| Pair | Task 4 → Task 5 | `EvaluationRun`, status, repository methods | Task 5 consumes durable run creation and adds queue/lease behavior. No contradiction. | Keep Worker persistence behind repository methods. |
| Pair | Task 4 → Task 6 | Evaluation repository and result query APIs | Task 6 consumes owned run lookup/list and result persistence. No contradiction. | Route layer must not bypass repositories. |
| Pair | Task 5 → Task 6 | enqueue-after-commit and status transitions | Task 6 creates/enqueues; Task 5 claims/runs. No contradiction. | Enqueue only after commit and make enqueue failure recoverable. |
| Pair | Task 5 → Task 7 | OpenAI client timeouts and Worker execution | Task 7 hardens the client used by Task 5. No contradiction. | Keep security validation in shared client/config boundary. |
| Pair | Task 6 → Task 8 | Health/readiness and route startup | Task 8 adds deployment/readiness after API is complete. No contradiction. | Integration test uses disposable services. |
| Own | Task 1 | Tests vs files | Tests refer to new Settings/database APIs created in the same task. | Consistent. |
| Own | Task 2 | Tests vs files | Tests target new user routes/dependencies created in the same task. | Consistent. |
| Own | Task 3 | Tests vs files | Tests target model route/service/security files created in the same task. | Consistent. |
| Own | Task 4 | Tests vs files | Tests target catalog/repository migration and the specified interfaces. | Consistent. |
| Own | Task 5 | Tests vs files | Tests target Redis queue and Worker behavior specified in the task. | Consistent. |
| Own | Task 6 | Tests vs files | Tests target v1 route and result response behavior specified in the task. | Consistent. |
| Own | Task 7 | Tests vs files | Tests target URL validation, rate limiting, and request IDs specified in the task. | Consistent. |
| Own | Task 8 | Tests vs files | Integration and deployment files cover the final system boundary. | Consistent. |

No plan contradiction requires a ruling before Task 1. The existing baseline failures will remain visible in the ledger and must not be silently reclassified as new-task regressions.

## Decisions

- **Ruling: Task 1 SQLite runtime finding is deferred to Task 4.** The spec requires the final API/Worker runtime to use PostgreSQL, but this plan deliberately assigns evaluation repository migration to Task 4. Rewriting the current SQLite task repository in Task 1 would duplicate Task 4's persistence work and create an unstable intermediate interface. Task 4 is therefore load-bearing: it must remove the live API/Worker dependency on `TaskRepository`/SQLite before Task 6 is accepted. Cost if wrong: the branch could temporarily retain SQLite longer than intended; the Task 4 gate prevents completion with that state.
- **Ruling: fix the legacy development secret check in Task 1.** Supporting the legacy environment variable is compatible with migration, but production validation must reject its unsafe default just as it rejects the new JWT secret default.
- **Ruling: live Alembic verification is environment-blocked, not code-approved.** PostgreSQL is not reachable and Docker is unavailable in this environment. Keep the verification requirement open in the ledger and require Task 8 integration/deployment verification to run it when services are available.
- **Ruling: Task 2 resource-isolation test is carried forward to Tasks 3 and 4.** Task 2 creates identity/authentication but no user-owned resource; adding a fake resource would test scaffolding rather than authorization behavior. Task 3 must add the concrete cross-user ModelProfile rejection test, and Task 4 must add the same check for EvaluationRun. Task 2's auth-only isolation tests are accepted within its actual scope.
- **Ruling: stale legacy `/api/me` route is deferred to the v1 route migration.** Task 2 keeps compatibility while Task 6 replaces legacy route wiring; remove or quarantine the conflicting dead route when v1 API routing is finalized.

## Task status

- Task 1: complete — commits `eb7a36b`, `f7b3ca6`; focused tests 11 passed; task review passed after fixing legacy production JWT-secret validation. PostgreSQL/Alembic live verification remains environment-blocked. SQLite removal is carried forward to Task 4 per ruling.
- Task 2: complete by ruling — commits `162177d`, `94ca853`; focused tests 11 passed; auth review found no core security defect. Concrete cross-user resource isolation is required in Tasks 3 and 4; stale legacy route cleanup is required by Task 6.
- Task 6: complete after review fix — commits `ac8762c`, `95a0f79`, `1ee17c2`, plus the final v1 error-envelope compatibility fix; full backend suite 154 passed, 2 skipped. All `/api/v1/*` errors now use the documented envelope, while legacy `/api/*` routes retain their compatibility response shape.
- Task 3: complete — commits `39a19bd`, `36c220a`; focused tests 11 passed; review approved after adding PATCH CORS preflight and timeout/network sanitization regression coverage.
- Task 4: complete — base commit `67feffa`, fix commit `bf62d2e`; final review approved. Verification: 62 passed, 1 explicit PostgreSQL integration skip. Migration, lease safety/recovery, fixed-admin FK protection, OpenAPI visibility, and user-owned run isolation are covered.
- Task 5: complete — commits `00d1707`, `bbec528`, `cff5b44`; final review approved. Verification: focused queue/worker/persistence tests passed with expected Redis/PostgreSQL integration skips. Redis Streams delivery, durable ack, lease requeue, and renewal-race protection are covered.
