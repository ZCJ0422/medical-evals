# Medical Evals 后端工作台设计

## 1. 目标与范围

后端是一个面向多用户的内部评测工作台。用户注册并登录后，可以保存自己的 OpenAI-compatible 模型连接配置，选择系统内置的 MedQA 或 HealthBench，创建异步评测任务，查看进度、汇总指标和受权限保护的样本结果。

第一版部署在一台云服务器上，但按可扩展的服务边界设计。第一版不支持用户上传数据集，也不支持非 OpenAI-compatible 的模型供应商。

## 2. 整体架构

```text
Frontend
   │ HTTPS + JWT
   ▼
API Service（FastAPI）
   ├── PostgreSQL：用户、模型配置、任务、进度、结果元数据
   ├── Redis：异步任务队列、短期状态、进度事件
   └── Worker：评测执行、checkpoint、结果聚合
                    │
                    ▼
             medical_evals 评测核心
                    │
                    ▼
        用户配置的 OpenAI-compatible API
```

API Service 不执行耗时评测，只负责认证、授权、请求校验、任务创建和查询。Worker 负责实际执行。`medical_evals` 保持为依赖中立的评测核心，CLI 和 Worker 通过各自的薄适配层调用它。

单机部署包含四类进程：`api`、`worker`、`postgres`、`redis`。前端独立部署，通过 HTTPS 调用 API。

## 3. 核心数据模型

### User

保存账户、密码哈希、角色和状态。角色为 `user` 或 `admin`，状态为 `active` 或 `disabled`。

### ModelProfile

保存用户的模型连接配置：名称、OpenAI-compatible `base_url`、`model_name` 和加密后的 API Key。API Key 只允许写入，不允许读取。

### EvaluationDefinition

表示系统内置评测定义。第一版包含 MedQA 和 HealthBench，并记录数据集版本、评测类型、默认配置和是否启用。用户不能上传或修改数据集内容。

### EvaluationRun

表示一次用户评测任务，包含用户、评测定义、目标模型、可选或必需的 Judge 模型、split、样本数、配置、状态、进度和时间信息。HealthBench 必须配置 Judge 模型。

### RunModelSnapshot

任务创建时保存目标模型和 Judge 模型的非秘密配置快照，保证用户之后修改 ModelProfile 不会改变历史任务的解释。API Key 仍然加密保存，不返回给前端。

### EvaluationResult 与 SampleResult

`EvaluationResult` 保存汇总指标、结果版本和 artifact 索引。`SampleResult` 保存样本编号、题目 ID、样本状态、得分、Judge JSON 和原始输出 artifact 引用。汇总结果默认直接返回，样本级结果分页读取。

所有用户资源查询都必须按 `user_id` 做服务端过滤。管理员可以查看全局任务状态，但默认不能读取用户 API Key 明文。

## 4. 任务执行模型

创建任务时，API 校验用户身份、资源归属、评测定义、模型配置以及 HealthBench 的 Judge 配置，然后创建 `queued` 任务并写入 Redis 队列，立即返回 `run_id`。

Worker 获取任务后将状态改为 `running`，加载评测定义和配置快照，逐条调用目标模型，必要时调用 Judge 模型，保存 checkpoint 和样本结果，持续更新进度，最后聚合指标并写入 `succeeded`。

状态机为：

```text
queued → running → succeeded
   │         │
   │         ├── failed
   │         └── cancelling → cancelled
   │
   └── cancelled
```

`queued` 可直接取消；运行中的任务通过持久化状态和取消信号通知 Worker 停止。终态不可继续修改。重试创建新的执行尝试，同时保留原始任务关联和错误记录。Redis 消费确认、数据库租约和唯一执行约束共同避免两个 Worker 并行处理同一任务。Worker 重启后，未完成任务可重新入队；checkpoint 允许从最近进度恢复。

PostgreSQL 是任务状态和进度的持久事实来源，Redis 只承担队列和加速通知。第一版前端采用轮询查询进度，后续再增加 SSE；第一版不引入 WebSocket。

## 5. API 边界

所有接口使用 `/api/v1` 前缀，并统一返回包含 `code`、`message` 和 `request_id` 的错误结构。

### 认证

```text
POST   /auth/register
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout
GET    /auth/me
```

使用短期 Access Token 和可撤销的 Refresh Token。密码使用 Argon2id 或 bcrypt 哈希。

### 模型配置

```text
GET    /models
POST   /models
GET    /models/{model_id}
PATCH  /models/{model_id}
DELETE /models/{model_id}
POST   /models/{model_id}/test
```

模型配置 API 只返回 `has_api_key`，不返回 Key。连接测试只返回成功或安全摘要错误。

### 评测定义

```text
GET /evaluation-definitions
GET /evaluation-definitions/{id}
```

返回内置评测、数据集版本、可用 split、默认样本数以及是否需要 Judge 模型。

### 评测任务

```text
GET    /evaluations
POST   /evaluations
GET    /evaluations/{run_id}
POST   /evaluations/{run_id}/cancel
POST   /evaluations/{run_id}/retry
DELETE /evaluations/{run_id}
```

创建请求包含评测定义、目标模型、Judge 模型（HealthBench）、split、样本数和评测配置。API 只创建任务，不同步等待执行完成。

### 结果

```text
GET /evaluations/{run_id}/summary
GET /evaluations/{run_id}/samples
GET /evaluations/{run_id}/artifacts
```

汇总接口返回指标和运行统计；样本接口分页返回样本结果；artifact 接口返回权限受控的下载能力。完整 Rubric、内部凭证和不必要的原始数据不进入普通结果响应。

## 6. 安全要求

- API Key 在数据库中加密保存，密钥只通过服务器环境变量注入。
- API Key 不进入日志、异常堆栈、任务元数据或前端响应。
- Worker 解密后仅在内存中使用。
- 生产环境强制 HTTPS。
- Base URL 做 SSRF 防护，禁止云元数据地址、内网地址和本机管理端口。
- 模型请求设置连接超时、读取超时、重试次数和并发限制。
- 注册、登录和模型测试接口限流。
- 资源授权在后端执行，不能依赖前端隐藏按钮。
- 每个请求生成 `request_id`，用于日志追踪。

错误分为配置错误、认证错误、模型请求错误、评测逻辑错误、基础设施错误和用户取消。内部异常、数据库细节和秘密信息不得返回给用户。

## 7. 测试与验收标准

测试分为单元测试、API 测试、Worker 测试、PostgreSQL/Redis 集成测试和安全测试。重点覆盖：权限隔离、状态机、指标聚合、凭证加解密、失败重试、取消、租约过期、断点恢复、重复提交和 SSRF 防护。

验收标准：

1. 用户 A 无法读取或操作用户 B 的模型、任务和结果。
2. API Key 不会明文出现在数据库、日志和 API 响应中。
3. API 重启不会丢失已创建的任务。
4. Worker 重启后任务可以恢复或明确失败。
5. 取消和重试不会产生两个并行执行实例。
6. CLI 和后端调用同一套评测核心，结果格式保持一致。

## 8. 第一阶段实现范围

第一阶段实现认证、用户隔离、模型配置、内置评测定义、异步评测任务、Worker、进度查询、取消/重试和汇总结果。管理后台、SSE、复杂报表、对象存储和更多模型供应商作为后续阶段。
