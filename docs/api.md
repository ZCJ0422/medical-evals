# Medical Evals API 设计

后端由 FastAPI 提供 HTTP/JSON API，默认监听 `:8000`。新客户端应优先使用 `/api/v1`；未带版本的 `/api` 路由是管理员工作台和旧版兼容接口。成功响应使用各 endpoint 的 Pydantic schema，删除操作通常返回 `204 No Content`。

## 1. 认证

除公开健康检查外，接口使用 `Authorization: Bearer <access_token>`。登录、注册或刷新成功后返回短期 access token 和一次性轮换的 refresh token：

```json
{
  "access_token": "<JWT>",
  "refresh_token": "<opaque-token>",
  "token_type": "bearer",
  "user": {"username": "alice", "role": "user", "status": "active"}
}
```

access token 默认有效 15 分钟，refresh token 默认有效 30 天。refresh 和 logout 会撤销当前 refresh token；刷新后客户端应替换本地保存的 token 对。

### 认证接口

| 方法 | 路径 | 权限 | 请求体 | 响应 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/auth/register` | 公开，带注册限流 | `{username, password}`，用户名 3–255 字符，密码 8–1024 字符 | `201 TokenResponse` |
| `POST` | `/api/v1/auth/login` | 公开，带登录限流 | `{username, password}` | `200 TokenResponse` |
| `POST` | `/api/v1/auth/refresh` | 携带 refresh token | `{refresh_token}` | `200 TokenResponse` |
| `POST` | `/api/v1/auth/logout` | 携带 refresh token | `{refresh_token}` | `204` |
| `GET` | `/api/v1/me` | 登录用户 | 无 | `{username, role, status}` |

相同的旧版认证路径位于 `/api/auth/*` 和 `/api/me`。管理员工作台还使用 `GET /api/me`，要求管理员身份。

## 2. 数据集目录与配置

### `GET /api/v1/datasets`

登录用户可读取已启用的评测定义：

```json
{
  "id": "medical-medqa",
  "name": "MedQA",
  "requires_judge": false,
  "splits": [
    {"id": "dev.v1", "dataset_version_id": "medical-medqa.dev.v1", "version": "dev.v1", "sample_count": 3425, "default_sample_limit": 3425}
  ],
  "default_split": "dev.v1",
  "default_sample_limit": 3425,
  "judge_model_id": null
}
```

### `PATCH /api/v1/datasets/{definition_id}/config`

仅管理员可调用，用于设置公众端提交时的默认值。

```json
{
  "default_split": "oss.v1",
  "default_sample_limit": 500,
  "judge_model_id": "<model-profile-id>"
}
```

`default_sample_limit` 范围为 1–10000，不能超过所选 split 的样本数；需要 Judge 的数据集必须提供 `judge_model_id`。成功返回更新后的 `EvaluationDefinitionResponse`。

## 3. 模型 profile

所有模型接口位于 `/api/v1/models`，要求登录用户，且只返回当前用户拥有的 profile。API key 只用于服务端连接测试或运行，响应只返回 `has_api_key`。

| 方法 | 路径 | 请求/响应 |
| --- | --- | --- |
| `GET` | `/api/v1/models` | 返回 `ModelProfilePublic[]` |
| `POST` | `/api/v1/models` | 请求 `{name, base_url, model_name, api_key}`；成功 `201 ModelProfilePublic` |
| `GET` | `/api/v1/models/{profile_id}` | 返回单个 profile |
| `PATCH` | `/api/v1/models/{profile_id}` | 可部分更新 `name`、`base_url`、`model_name`、`api_key` |
| `DELETE` | `/api/v1/models/{profile_id}` | 删除 profile，返回 `204` |
| `POST` | `/api/v1/models/{profile_id}/test` | 测试供应商连接，返回 `{"ok": true}`；该接口带限流 |

`base_url` 必须是完整 HTTP(S) URL，不能包含内嵌凭据，也不能解析到 loopback、私网、链路本地或云 metadata 地址。`deepseek-v4*` 连接测试会关闭 thinking，以避免测试请求产生不必要的推理输出。

## 4. 测评运行

### 创建请求

`POST /api/v1/evaluations` 要求登录用户。请求体：

```json
{
  "name": "可选运行名称",
  "evaluation_definition_id": "medical-healthbench",
  "target_model_id": "<target-profile-id>",
  "judge_model_id": "<judge-profile-id>",
  "split": "smoke.v1",
  "sample_limit": 2,
  "config": {}
}
```

`split`、`sample_limit` 和 Judge 可省略，服务端会使用数据集统一配置。成功返回 `201 EvaluationRunResponse`，并立即把运行放入 Redis Streams。

### 运行响应

```json
{
  "run_id": "<uuid>",
  "name": "HealthBench-…",
  "evaluation_definition_id": "medical-healthbench",
  "target_model_id": "<uuid>",
  "judge_model_id": "<uuid>",
  "dataset_version_id": "medical-healthbench.smoke.v1",
  "status": "queued",
  "progress": {
    "completed_count": 0,
    "total_count": 2,
    "progress_percent": 0,
    "success_count": 0,
    "failed_count": 0,
    "retry_count": 0,
    "stage": "queued"
  },
  "split": "smoke.v1",
  "sample_limit": 2,
  "config": {},
  "created_at": "2026-09-09T01:00:00Z",
  "updated_at": "2026-09-09T01:00:00Z",
  "queued_at": "2026-09-09T01:00:00Z",
  "started_at": null,
  "finished_at": null,
  "retry_of_run_id": null,
  "error": null
}
```

### 运行接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/evaluations` | 当前用户的运行列表；管理员可看全局。查询参数：`status`、`limit`（1–200）、`offset`、`created_after`、`created_before` |
| `POST` | `/api/v1/evaluations` | 创建并入队运行，返回 `201` |
| `GET` | `/api/v1/evaluations/{run_id}` | 查询单次运行 |
| `POST` | `/api/v1/evaluations/{run_id}/cancel` | 仅 `queued` 或 `running` 可取消 |
| `POST` | `/api/v1/evaluations/{run_id}/retry` | 仅终态运行可重试；创建新 run 并设置 `retry_of_run_id` |
| `DELETE` | `/api/v1/evaluations/{run_id}` | 不能直接删除运行中的任务；先取消后删除，返回 `204` |

公开状态为 `queued`、`running`、`cancelled`、`succeeded`、`failed`。内部 `completed` 和 `partial_failed` 对外统一映射为 `succeeded`，详细失败数位于 progress/summary。

旧版管理员接口位于 `/api/evaluations`，另外提供 `POST /preflight`、`GET /{task_id}/progress`、`POST /{task_id}/resume` 等兼容能力。新前端不应依赖这些未版本化接口。

## 5. 结果与工件

### 运行结果

| 方法 | 路径 | 返回 |
| --- | --- | --- |
| `GET` | `/api/v1/evaluations/{run_id}/summary` | `EvaluationSummaryResponse`：总分、准确率、解析成功率、维度分数、错误分类、完成/失败/重试计数，并返回 `result_version` |
| `GET` | `/api/v1/evaluations/{run_id}/samples?offset=0&limit=50` | `EvaluationSamplesResponse`；`limit` 范围 1–200，含 `total` 和 `has_more` |
| `GET` | `/api/v1/evaluations/{run_id}/artifacts` | 工件清单：`report.html`、`run.log`、`events.jsonl`、`summary.json`、`metadata.json`、`samples.jsonl`、`manifest.json` |
| `GET` | `/api/v1/evaluations/{run_id}/artifacts/{artifact_name}` | 下载单个工件，服务端校验允许的文件名 |

所有结果接口都执行运行可见性检查：管理员可访问全局运行，普通用户只能访问自己创建的运行。兼容接口 `/api/evaluations/{task_id}/results`、`/samples`、`/log`、`/report` 和 `/report/generate` 只面向管理员。

## 6. 健康检查

| 方法 | 路径 | 语义 |
| --- | --- | --- |
| `GET` | `/healthz` | 进程存活，返回 `{"status":"ok"}` |
| `GET` | `/readyz` | 检查数据库连接；可用时返回 `{"status":"ready","database":"ok"}`，不可用时返回 `503` |

## 7. 运行监控

### `GET /api/v1/ops/metrics`

仅管理员可调用。接口聚合 Redis Streams、运行表、结果摘要和 artifact 目录的当前快照，用于后台看板和告警采集：

```json
{
  "generated_at": "2026-09-09T01:00:00Z",
  "queue_depth": 4,
  "queue_pending": 2,
  "queue_error": null,
  "status_counts": {"queued": 1, "running": 1},
  "expired_leases": 1,
  "failure_categories": {"timeout": 2, "parse": 1},
  "request_success_count": 10,
  "parse_failed_count": 2,
  "parse_success_rate": 0.8,
  "artifact_bytes": 1048576,
  "artifact_file_count": 12
}
```

Redis 暂时不可用时，`queue_depth`、`queue_pending` 返回 `null`，并在 `queue_error` 返回 Redis 异常信息（仅管理员可见）；其余数据库和 artifact 指标仍会返回。`parse_success_rate` 在没有请求样本时为 `null`。

## 8. 错误格式与状态码

`/api/v1/*` 使用统一错误 envelope：

```json
{
  "error": {
    "code": "evaluation_run_not_found",
    "message": "Evaluation run not found",
    "request_id": "<uuid>"
  }
}
```

API 同时在响应头返回 `X-Request-ID`。常见状态码：

| 状态码 | 场景 |
| --- | --- |
| `400` | 请求语义错误 |
| `401` | 缺少、过期或无效 Bearer token |
| `403` | 账户禁用或需要管理员权限 |
| `404` | 运行、模型、数据集或工件不存在，或对当前用户不可见 |
| `409` | 状态冲突，例如运行中不能删除、未完成不能重试 |
| `422` | Pydantic 字段校验、分页参数、模型 URL、评测依赖或配置错误 |
| `429` | 注册、登录或模型连接测试超过限流 |
| `503` | 生产环境 Redis 限流不可用，或 readiness 数据库不可用 |

未版本化 `/api/*` 兼容路由保留 FastAPI 风格的 `{"detail": ...}` 错误体，不应与 v1 envelope 混用。

## 9. 典型调用顺序

```text
POST /api/v1/auth/login
  └─ GET /api/v1/datasets
  └─ POST /api/v1/models
  └─ POST /api/v1/evaluations
       └─ 轮询 GET /api/v1/evaluations/{run_id}
       └─ GET /api/v1/evaluations/{run_id}/summary
       └─ GET /api/v1/evaluations/{run_id}/samples?offset=0&limit=50
       └─ GET /api/v1/evaluations/{run_id}/artifacts
```

当 access token 返回 `401` 时，客户端应调用 refresh，替换 token 对后重试原请求；若 refresh 失败则清除本地认证状态并要求重新登录。
