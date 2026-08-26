# Medical Evals Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有单管理员、SQLite 工作台后端升级为支持多用户注册登录、用户级资源隔离、OpenAI-compatible 模型配置和异步评测任务的 FastAPI + PostgreSQL + Redis + Worker 后端。

**Architecture:** FastAPI API 负责认证、授权、校验、任务创建和查询；PostgreSQL 保存所有持久状态；Redis 提供任务队列和取消信号；独立 Worker 调用现有 `medical_evals` 评测核心并保存 checkpoint、样本结果和汇总指标。CLI 与 Worker 继续共享评测核心，但不共享入口层。

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, `psycopg`, Redis 5+, Argon2id, JWT, pytest/httpx。

**Spec:** `docs/superpowers/specs/2026-08-26-backend-workbench-design.md`

## Global Constraints

- 第一版只支持内置 MedQA 和 HealthBench，不支持用户上传数据集。
- 第一版只支持 OpenAI-compatible API：`base_url`、`api_key`、`model_name`。
- HealthBench 必须配置独立 Judge 模型；MedQA 不需要 Judge。
- API Key 在数据库中加密保存，不能出现在日志、错误、任务元数据或 API 响应中。
- 普通用户只能访问自己的模型配置、评测任务、结果和 artifacts；管理员权限必须在后端显式校验。
- PostgreSQL 是任务状态和进度的事实来源；Redis 只承担队列和短期信号。
- 任务必须支持 queued、running、cancelling、cancelled、succeeded、failed 状态，以及取消、重试、checkpoint 恢复和防重复执行。
- 不改变 `medical_evals` 核心的 CLI 注册名、结果字段和现有评测语义。
- 当前工作区已有的 frontend、core 和 backend 修改属于用户现有工作；实施时只修改本计划列出的相关文件。

---

### Task 1: 建立 PostgreSQL/Redis 配置与数据库迁移基础

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/medical_evals_api/config.py`
- Modify: `backend/medical_evals_api/db.py`
- Create: `backend/medical_evals_api/database.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial_workbench.py`
- Modify: `backend/.env.example`
- Create: `backend/tests/test_database_config.py`

**Interfaces:**
- Produces `get_session() -> Iterator[Session]` for API dependencies.
- Produces `get_redis() -> redis.Redis` for queue services.
- Produces `Settings.database_url`, `Settings.redis_url`, `Settings.jwt_secret`, `Settings.encryption_secret`.
- Replaces the runtime dependency on `sqlite3` for new API and Worker paths; keep a read-only migration utility only if needed to inspect old local data.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_settings_read_postgres_and_redis_urls(monkeypatch):
    monkeypatch.setenv("MEDICAL_EVALS_DATABASE_URL", "postgresql+psycopg://u:p@db/medical")
    monkeypatch.setenv("MEDICAL_EVALS_REDIS_URL", "redis://redis:6379/0")
    settings = Settings()
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.redis_url == "redis://redis:6379/0"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `cd backend && uv run pytest tests/test_database_config.py -q`

Expected: FAIL because the new settings and database session factory do not exist.

- [ ] **Step 3: Add dependencies, settings, SQLAlchemy engine/session factory, Redis client, and Alembic bootstrap**

Use a synchronous SQLAlchemy engine so existing synchronous FastAPI routes and Worker code can migrate without introducing an async database boundary. Configure pool pre-ping and bounded pool size for the single-cloud-server deployment.

- [ ] **Step 4: Add the initial migration with UUID/string IDs, timestamps, and enum-compatible status strings**

The migration must create `users`, `refresh_tokens`, `model_profiles`, `evaluation_definitions`, `evaluation_runs`, `run_model_snapshots`, `evaluation_results`, and `evaluation_sample_results` with indexes on `user_id`, `status`, and `(run_id, sample_index)`.

- [ ] **Step 5: Run the focused test and migration check**

Run: `cd backend && uv run pytest tests/test_database_config.py -q`

Expected: PASS. Run `cd backend && uv run alembic check` against a disposable PostgreSQL database and verify no untracked schema change is reported.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/medical_evals_api/config.py backend/medical_evals_api/db.py backend/medical_evals_api/database.py backend/alembic.ini backend/alembic backend/.env.example backend/tests/test_database_config.py
git commit -m "feat: add postgres and redis backend foundations"
```

### Task 2: Implement multi-user authentication and authorization

**Files:**
- Modify: `backend/medical_evals_api/auth.py`
- Modify: `backend/medical_evals_api/routes/auth.py`
- Create: `backend/medical_evals_api/models/users.py`
- Create: `backend/medical_evals_api/repositories/users.py`
- Create: `backend/medical_evals_api/schemas/users.py`
- Modify: `backend/medical_evals_api/main.py`
- Modify: `backend/tests/test_auth.py`
- Create: `backend/tests/test_user_isolation.py`

**Interfaces:**
- Produces `CurrentUser = Annotated[User, Depends(require_user)]`.
- Produces `require_user(request) -> User` and `require_admin(request) -> User`.
- Produces `POST /api/v1/auth/register`, `/login`, `/refresh`, `/logout`, and `GET /me`.
- Produces password helpers `hash_password(password: str) -> str` and `verify_password(password: str, digest: str) -> bool` using Argon2id.

- [ ] **Step 1: Add failing tests for registration, login, refresh-token revocation, disabled users, and cross-user rejection**

```python
def test_user_cannot_read_another_users_resource(client, user_a_token, user_b_model_id):
    response = client.get(f"/api/v1/models/{user_b_model_id}", headers=auth(user_a_token))
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify the current fixed-admin implementation fails the new cases**

Run: `cd backend && uv run pytest tests/test_auth.py tests/test_user_isolation.py -q`

Expected: FAIL because the current auth model only supports the fixed administrator/public identities.

- [ ] **Step 3: Replace fixed-password identity checks with database-backed users, Argon2id password hashes, short-lived JWT access tokens, and hashed refresh-token records**

Do not include API keys or other secrets in token claims. Return generic login errors so account existence is not disclosed.

- [ ] **Step 4: Add route dependencies and explicit role checks**

Every protected route must receive the current user from the dependency layer. Admin routes must verify `user.role == "admin"`; frontend visibility is not an authorization mechanism.

- [ ] **Step 5: Run focused auth and isolation tests**

Run: `cd backend && uv run pytest tests/test_auth.py tests/test_user_isolation.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/medical_evals_api/auth.py backend/medical_evals_api/routes/auth.py backend/medical_evals_api/models/users.py backend/medical_evals_api/repositories/users.py backend/medical_evals_api/schemas/users.py backend/medical_evals_api/main.py backend/tests/test_auth.py backend/tests/test_user_isolation.py
git commit -m "feat: add multi-user authentication and authorization"
```

### Task 3: Add model profiles and encrypted credential handling

**Files:**
- Modify: `backend/medical_evals_api/secrets.py`
- Create: `backend/medical_evals_api/models/model_profiles.py`
- Create: `backend/medical_evals_api/repositories/model_profiles.py`
- Create: `backend/medical_evals_api/schemas/model_profiles.py`
- Create: `backend/medical_evals_api/services/model_profiles.py`
- Create: `backend/medical_evals_api/routes/models.py`
- Modify: `backend/medical_evals_api/main.py`
- Create: `backend/tests/test_model_profiles.py`
- Create: `backend/tests/test_model_security.py`

**Interfaces:**
- Produces `ModelProfileService.create(user_id, payload) -> ModelProfilePublic`.
- Produces `ModelProfileService.resolve_secret(profile_id, user_id) -> ModelCredentials` for Worker-only use.
- Produces `POST/GET/PATCH/DELETE /api/v1/models` and `POST /api/v1/models/{id}/test`.
- Public schemas contain `has_api_key: bool`, never `api_key`.

- [ ] **Step 1: Write failing tests for ownership, write-only API keys, encrypted storage, OpenAI-compatible URL validation, and safe connection-test errors**

```python
def test_model_response_never_contains_api_key(client, token):
    response = client.post("/api/v1/models", headers=auth(token), json=payload_with_key())
    assert "api_key" not in response.json()
    assert response.json()["has_api_key"] is True
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd backend && uv run pytest tests/test_model_profiles.py tests/test_model_security.py -q`

Expected: FAIL because model profiles and user-owned credentials do not exist.

- [ ] **Step 3: Implement encrypted-at-rest model profiles and write-only schemas**

Use authenticated encryption with the configured master key. Reject non-HTTP(S) URLs, credentials embedded in URLs, and empty model names. Store only the encrypted key and non-secret connection metadata.

- [ ] **Step 4: Implement the connection-test service with timeouts, no key logging, and sanitized provider errors**

The test endpoint must execute a minimal compatible request through the same client factory as Worker, but must never persist the test response or return provider request headers.

- [ ] **Step 5: Run focused tests and commit**

Run: `cd backend && uv run pytest tests/test_model_profiles.py tests/test_model_security.py -q`

Expected: PASS.

```bash
git add backend/medical_evals_api/secrets.py backend/medical_evals_api/models/model_profiles.py backend/medical_evals_api/repositories/model_profiles.py backend/medical_evals_api/schemas/model_profiles.py backend/medical_evals_api/services/model_profiles.py backend/medical_evals_api/routes/models.py backend/medical_evals_api/main.py backend/tests/test_model_profiles.py backend/tests/test_model_security.py
git commit -m "feat: add user-owned encrypted model profiles"
```

### Task 4: Migrate catalog and evaluation persistence to user-owned PostgreSQL records

**Files:**
- Modify: `backend/medical_evals_api/models.py`
- Modify: `backend/medical_evals_api/repositories/tasks.py`
- Modify: `backend/medical_evals_api/evaluation_sources.py`
- Modify: `backend/medical_evals_api/routes/catalog.py`
- Modify: `backend/medical_evals_api/schemas/evaluations.py`
- Create: `backend/medical_evals_api/models/evaluations.py`
- Create: `backend/medical_evals_api/repositories/evaluations.py`
- Create: `backend/tests/test_evaluation_persistence_postgres.py`
- Modify: `backend/tests/test_catalog_routes.py`

**Interfaces:**
- Produces `EvaluationRepository.create(user_id, create_command) -> EvaluationRun`.
- Produces `EvaluationRepository.get_owned(run_id, user_id) -> EvaluationRun | None`.
- Produces `EvaluationRepository.list_owned(user_id, filters) -> list[EvaluationRun]`.
- Produces catalog records for fixed `medqa` and `healthbench` definitions, including version, split, sample limits, and `requires_judge`.

- [ ] **Step 1: Write failing tests for fixed catalog data, user ownership, HealthBench Judge validation, and model snapshot creation**

```python
def test_healthbench_requires_judge_profile(client, token, target_model_id):
    response = client.post("/api/v1/evaluations", headers=auth(token), json={
        "evaluation_definition_id": "healthbench",
        "target_model_id": target_model_id,
        "sample_limit": 1,
    })
    assert response.status_code == 422
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd backend && uv run pytest tests/test_catalog_routes.py tests/test_evaluation_persistence_postgres.py -q`

Expected: FAIL because the current repository stores admin-owned SQLite tasks and accepts legacy request fields.

- [ ] **Step 3: Implement SQLAlchemy repositories and seed only the two built-in evaluation definitions**

Keep dataset content in the existing registry/data locations. Store a definition/version reference, not a user-uploaded file.

- [ ] **Step 4: Update evaluation schemas and route dependencies**

Use the API contract from the spec: `evaluation_definition_id`, target model profile, optional Judge profile, split, sample limit, and JSON config. On create, copy non-secret model metadata into `run_model_snapshots` and enqueue only after the transaction commits.

- [ ] **Step 5: Run persistence, catalog, and existing compatibility tests**

Run: `cd backend && uv run pytest tests/test_catalog_routes.py tests/test_evaluation_persistence_postgres.py tests/test_medqa_core_parity.py tests/test_healthbench_metrics.py -q`

Expected: PASS, with existing core parity tests unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/medical_evals_api/models.py backend/medical_evals_api/repositories/tasks.py backend/medical_evals_api/evaluation_sources.py backend/medical_evals_api/routes/catalog.py backend/medical_evals_api/schemas/evaluations.py backend/medical_evals_api/models/evaluations.py backend/medical_evals_api/repositories/evaluations.py backend/tests/test_catalog_routes.py backend/tests/test_evaluation_persistence_postgres.py
git commit -m "feat: persist user-owned evaluation runs in postgres"
```

### Task 5: Replace the local queue with Redis enqueueing and durable Worker leases

**Files:**
- Modify: `backend/medical_evals_api/queue.py`
- Create: `backend/medical_evals_api/redis_queue.py`
- Modify: `backend/medical_evals_api/worker.py`
- Modify: `backend/medical_evals_api/cli.py`
- Modify: `backend/medical_evals_api/repositories/evaluations.py`
- Create: `backend/tests/test_redis_queue.py`
- Modify: `backend/tests/test_worker.py`
- Modify: `backend/tests/test_real_worker.py`

**Interfaces:**
- Produces `RedisTaskQueue.enqueue(run_id: str) -> None`.
- Produces `RedisTaskQueue.claim(run_id: str, worker_id: str) -> bool` using a Redis Streams consumer group or equivalent reliable queue primitive.
- Produces `Worker.run_task(run_id: str) -> EvaluationRun` with lease renewal and checkpoint callbacks.
- Produces `Worker.run_forever()` for the CLI worker command.

- [ ] **Step 1: Write failing queue and worker tests**

Cover enqueue/dequeue acknowledgement, duplicate delivery, lease renewal, expired lease recovery, cancellation polling, and no progress writes after lease loss.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd backend && uv run pytest tests/test_redis_queue.py tests/test_worker.py tests/test_real_worker.py -q`

Expected: FAIL because the current `LocalTaskQueue` does not enqueue into Redis and the repository is SQLite-backed.

- [ ] **Step 3: Implement Redis queue and PostgreSQL lease operations**

Use an idempotency key based on `run_id`, claim with a lease owner and expiry, acknowledge only after a durable terminal state, and requeue expired claims. Redis outages must leave the PostgreSQL task visible as queued or recoverable rather than marking it successful.

- [ ] **Step 4: Adapt the existing Worker to model snapshots, encrypted credential resolution, cancellation, checkpoint resume, sample progress, and aggregate result persistence**

Preserve the current `EvaluationAdapter` and `build_run_metrics` behavior. Do not move evaluation algorithms into routes.

- [ ] **Step 5: Run worker and parity tests**

Run: `cd backend && uv run pytest tests/test_redis_queue.py tests/test_worker.py tests/test_real_worker.py tests/test_medqa_core_parity.py tests/test_healthbench_real_worker.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/medical_evals_api/queue.py backend/medical_evals_api/redis_queue.py backend/medical_evals_api/worker.py backend/medical_evals_api/cli.py backend/medical_evals_api/repositories/evaluations.py backend/tests/test_redis_queue.py backend/tests/test_worker.py backend/tests/test_real_worker.py
git commit -m "feat: add redis evaluation queue and durable worker leases"
```

### Task 6: Implement versioned `/api/v1` evaluation and result APIs

**Files:**
- Modify: `backend/medical_evals_api/routes/evaluations.py`
- Modify: `backend/medical_evals_api/routes/results.py`
- Modify: `backend/medical_evals_api/routes/reports.py`
- Modify: `backend/medical_evals_api/schemas/common.py`
- Modify: `backend/medical_evals_api/schemas/evaluations.py`
- Create: `backend/medical_evals_api/schemas/results.py`
- Modify: `backend/medical_evals_api/main.py`
- Create: `backend/tests/test_v1_evaluation_routes.py`
- Modify: `backend/tests/test_results_security.py`

**Interfaces:**
- Implements `GET/POST /api/v1/evaluations`, `GET /api/v1/evaluations/{run_id}`, `POST .../cancel`, `POST .../retry`, and `DELETE ...`.
- Implements `GET /api/v1/evaluations/{run_id}/summary`, `/samples`, and `/artifacts`.
- Returns the common error envelope `{ "error": { "code": str, "message": str, "request_id": str } }`.

- [ ] **Step 1: Write failing route tests for create, list, detail, cancel, retry, pagination, and cross-user access**

Assert that create returns `201` with a `run_id` immediately, list/detail only return owned records, and terminal state transitions return `409` when invalid.

- [ ] **Step 2: Run focused route tests and verify failure**

Run: `cd backend && uv run pytest tests/test_v1_evaluation_routes.py tests/test_results_security.py -q`

Expected: FAIL because current routes use `/api/evaluations`, fixed admin auth, and legacy task fields.

- [ ] **Step 3: Implement v1 routes with transaction-safe enqueue-after-commit behavior**

A failed Redis enqueue must leave the task in a visible recoverable state. List endpoints must support status/date pagination without loading all sample results.

- [ ] **Step 4: Implement summary and paginated sample responses**

Return aggregate metrics by default. Keep raw outputs and complete HealthBench rubric judgments behind authenticated, ownership-checked sample/artifact endpoints.

- [ ] **Step 5: Run focused and existing result tests**

Run: `cd backend && uv run pytest tests/test_v1_evaluation_routes.py tests/test_results_security.py tests/test_result_persistence.py tests/test_reports.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/medical_evals_api/routes/evaluations.py backend/medical_evals_api/routes/results.py backend/medical_evals_api/routes/reports.py backend/medical_evals_api/schemas/common.py backend/medical_evals_api/schemas/evaluations.py backend/medical_evals_api/schemas/results.py backend/medical_evals_api/main.py backend/tests/test_v1_evaluation_routes.py backend/tests/test_results_security.py
git commit -m "feat: expose multi-user evaluation and result APIs"
```

### Task 7: Add SSRF, rate limiting, request tracing, and production configuration checks

**Files:**
- Modify: `backend/medical_evals_api/config.py`
- Modify: `backend/medical_evals_api/openai_compatible.py`
- Create: `backend/medical_evals_api/security.py`
- Modify: `backend/medical_evals_api/main.py`
- Create: `backend/tests/test_security_hardening.py`
- Modify: `backend/.env.example`

**Interfaces:**
- Produces `validate_public_base_url(url: str) -> AnyHttpUrl` with blocked loopback, link-local, private, metadata, and non-HTTP(S) destinations.
- Produces request ID middleware that adds `X-Request-ID` to responses and structured logs.
- Produces rate-limit dependencies for registration, login, and model test endpoints.

- [ ] **Step 1: Write failing security tests**

Reject `127.0.0.1`, `localhost`, RFC1918 ranges, IPv6 loopback, cloud metadata addresses, credentials in URLs, and unsupported schemes. Confirm sanitized errors do not contain API keys.

- [ ] **Step 2: Run focused security tests and verify failure**

Run: `cd backend && uv run pytest tests/test_security_hardening.py -q`

Expected: FAIL until URL validation and middleware are installed.

- [ ] **Step 3: Implement URL validation, timeouts, provider-error sanitization, request IDs, and Redis-backed rate limiting**

Keep an explicit development-only localhost override behind `environment == "development"`; production must fail closed.

- [ ] **Step 4: Run security and auth tests**

Run: `cd backend && uv run pytest tests/test_security_hardening.py tests/test_auth.py tests/test_model_security.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/medical_evals_api/config.py backend/medical_evals_api/openai_compatible.py backend/medical_evals_api/security.py backend/medical_evals_api/main.py backend/tests/test_security_hardening.py backend/.env.example
git commit -m "feat: harden backend security and production configuration"
```

### Task 8: Add single-server deployment, health checks, and end-to-end verification

**Files:**
- Create: `deploy/docker-compose.backend.yml`
- Create: `deploy/backend.Dockerfile`
- Modify: `backend/scripts/run_api.sh`
- Modify: `backend/scripts/run_worker.sh`
- Modify: `backend/medical_evals_api/main.py`
- Modify: `backend/README.md`
- Create: `backend/tests/test_backend_integration.py`
- Create: `deploy/README.md`

**Interfaces:**
- API health endpoint reports API and PostgreSQL readiness without exposing secrets.
- Worker health/heartbeat is visible to the admin health check.
- Compose starts PostgreSQL, Redis, API, and Worker with persistent volumes for database and protected artifacts.

- [ ] **Step 1: Write the integration test against disposable PostgreSQL and Redis services**

The test must register two users, create isolated model profiles, create a MedQA task, observe queue-to-worker completion with a fake OpenAI-compatible adapter, cancel one task, retry a failed task, and verify the other user cannot access any resource.

- [ ] **Step 2: Run the integration test before deployment changes**

Run: `cd backend && uv run pytest tests/test_backend_integration.py -q`

Expected: FAIL until all prior tasks are connected.

- [ ] **Step 3: Add Docker Compose, environment documentation, migrations-on-start instructions, artifact volume permissions, and separate API/Worker commands**

Do not bake secrets into the image. Require `MEDICAL_EVALS_DATABASE_URL`, `MEDICAL_EVALS_REDIS_URL`, JWT secret, encryption secret, and an admin bootstrap mechanism in production.

- [ ] **Step 4: Run full backend verification**

Run:

```bash
cd backend
uv run pytest -q
uv run python -m medical_evals_api.cli --help
```

Expected: all backend tests pass, CLI exposes API/Worker/migration commands, and no test logs contain API key material.

- [ ] **Step 5: Commit**

```bash
git add deploy/docker-compose.backend.yml deploy/backend.Dockerfile backend/scripts/run_api.sh backend/scripts/run_worker.sh backend/medical_evals_api/main.py backend/README.md deploy/README.md backend/tests/test_backend_integration.py
git commit -m "feat: add single-server backend deployment and integration checks"
```

## Plan Self-Review

- Spec architecture is covered by Tasks 1, 5, and 8.
- User/auth/permission requirements are covered by Tasks 2 and 6.
- Model credential encryption and OpenAI-compatible constraints are covered by Task 3 and Task 7.
- Built-in MedQA/HealthBench catalog and Judge validation are covered by Task 4.
- Queue, leases, cancellation, retry, checkpoint, and duplicate execution controls are covered by Task 5.
- Result persistence, artifacts, pagination, and protected raw samples are covered by Tasks 4 and 6.
- Security, error handling, testing, and single-server deployment are covered by Tasks 7 and 8.
- No unresolved placeholders or unspecified “appropriate handling” steps remain.
