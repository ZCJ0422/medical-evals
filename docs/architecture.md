# Medical Evals 系统架构

本文描述 `medical-evals` 当前实现的组件边界、评测请求路径、异步执行路径和部署形态。架构图由 Archify 根据代码证据生成：

- [交互式架构图](./architecture.html)
- [Archify 架构图规格](./architecture.architecture.json)

图表是此前生成的架构快照，本次未重新进行视觉验收。图中引用的代码证据固定在提交 `4163ef02d22d7a3de5452cb7dc99a432efc19ac7`，对应仓库 `https://github.com/ZCJ0422/medical-evals`。

## 1. 架构概览

系统分为请求平面、执行平面和模型/证据平面：

```text
浏览器
  │ HTTP/JSON
  ▼
Next.js Web UI ── FastAPI API ── PostgreSQL
                         │             └─ 用户、模型配置、测评运行、进度与结果
                         │ enqueue
                         ▼
                    Redis Streams ── Evaluation Worker ── Evaluation Core
                                                           │             ├─ Target Model API
                                                           │             └─ Judge Model API（可选）
                                                           ├─ Dataset Registry
                                                           └─ Artifact Storage
```

Next.js 同时承载公众端门户和管理员工作台。FastAPI 是认证、数据集目录、模型配置、测评运行、结果和报告接口的统一入口。PostgreSQL 保存系统状态；Redis Streams 负责把排队的测评交给 Worker；Worker 调用共享的 `medical_evals` 核心逻辑，逐样本更新状态并写出结果工件。

## 2. 组件与职责

| 组件 | 职责 | 代码证据 |
| --- | --- | --- |
| Next.js Web UI | 公众提交测评、查看提交记录；管理员管理模型、测评和统一配置 | `frontend/app/page.tsx`、`frontend/components/app-shell.tsx` |
| FastAPI API | 注册路由、认证、CORS、请求 ID、错误封装、健康检查 | `backend/medical_evals_api/main.py` |
| Evaluation routes | 创建、查询、取消、重试测评并将排队任务交给队列 | `backend/medical_evals_api/routes/evaluations.py` |
| PostgreSQL | 用户、模型 profile、数据集配置、运行状态、进度、摘要和样本结果的持久化来源 | `backend/medical_evals_api/database.py`、`backend/medical_evals_api/models/` |
| Redis Streams | 以 consumer group 投递测评任务；通过 dedupe key 避免重复入队；支持 pending message reclaim | `backend/medical_evals_api/redis_queue.py` |
| Evaluation Worker | 获取任务 lease、恢复/重置中断任务、刷新心跳、记录进度、确认终态消息 | `backend/medical_evals_api/worker.py` |
| Evaluation Core | 运行 MedQA 与 HealthBench，处理重试、解析、聚合和评分 | `backend/medical_evals_api/evaluator_adapter.py`、`medical_evals/core/` |
| Dataset Registry | 提供版本化的 MedQA/HealthBench 数据集和评测定义 | `registry/evals/`、`registry/data/` |
| OpenAI-compatible clients | 调用用户配置的 Target 模型和可选 Judge 模型，统一解析兼容响应 | `backend/medical_evals_api/openai_compatible.py`、`medical_evals/core/openai_compatible.py` |
| Artifact Storage | 保存运行元数据、逐样本记录、日志、checkpoint 和 summary；部署时挂载共享卷 | `backend/medical_evals_api/artifacts.py`、`deploy/docker-compose.backend.yml` |

## 3. 关键调用路径

### 3.1 提交测评

1. 浏览器从 Next.js 门户提交模型 endpoint、API key 和数据集选择。
2. FastAPI 校验身份、请求字段、公开 URL 和模型配置，并将 API key 加密保存。
3. `EvaluationRepository` 根据数据集默认配置补齐 split、样本上限和 Judge profile，创建 `queued` 运行记录。
4. `LocalTaskQueue` 在生产型 repository 上委托给 `RedisTaskQueue`，通过 Lua 脚本写入 Redis Stream 并设置去重键。
5. API 立即返回运行摘要；前端随后通过运行列表、summary 和 samples 接口读取状态。

### 3.2 Worker 执行

1. Worker 以 consumer 身份从 Redis Streams 获取消息，或回收超过 lease 时间的 pending 消息。
2. Worker 从 PostgreSQL 再次确认任务状态并取得 lease；PostgreSQL 是任务状态的权威来源。
3. 根据数据集版本加载 Registry 样本，写入 `EvalRunMetadata` 和初始日志。
4. Evaluation Core 为每个样本调用 Target Model；HealthBench 在需要时再调用 Judge Model，并产生 rubric 结果。
5. 每个样本写入 checkpoint、artifact 和数据库结果；阶段、完成数、失败数和重试数持续回写 PostgreSQL。
6. 成功、部分失败、失败或取消后，Worker 写入 summary，确认 Redis 消息，并关闭模型客户端。

### 3.3 结果读取

管理员或任务所属公众用户通过结果接口读取运行摘要、日志、样本分页和报告。权限过滤在 repository 层执行：管理员可查看全局运行，普通用户只能访问自己创建的运行和模型 profile。

## 4. 部署形态

`deploy/docker-compose.backend.yml` 定义四个运行服务：

- `postgres`：PostgreSQL 16，挂载 `medical-evals-postgres` volume。
- `redis`：Redis 7，挂载 `medical-evals-redis` volume。
- `api`：构建后端镜像，启动时执行数据库初始化并运行 FastAPI，暴露 `8000`，挂载 artifact volume。
- `worker`：使用同一后端镜像运行 Worker，和 API 共享 artifact volume，并依赖 PostgreSQL 与 Redis 健康检查。

前端作为独立 Next.js 应用运行；后端通过 `MEDICAL_EVALS_DATABASE_URL` 和 `MEDICAL_EVALS_REDIS_URL` 连接 PostgreSQL/Redis。API 的 `/healthz` 只表示进程存活，`/readyz` 会实际执行数据库连接检查。

## 5. 一致性、恢复与安全边界

- PostgreSQL 保存最终任务状态；Redis 不可用时，入队调用会保留数据库状态，Worker 的 reconcile 流程可在 Redis 恢复后重新填充队列。
- Worker lease、heartbeat 和 stale-message reclaim 防止 Worker 中断后任务永久悬挂；checkpoint 允许从已写入样本继续。
- API 为每次请求生成 `X-Request-ID`；`/api/v1` 错误统一为带 code、message 和 request_id 的 envelope。
- API key 只以加密形式持久化，运行 metadata 明确记录 `credentials_recorded: false`；原始模型输出可按运行策略写入 artifacts。
- CORS 由配置的前端 origin 控制；模型 endpoint 经过公开 URL 校验；普通用户的运行和模型 profile 通过 user ownership 隔离。
- Judge Model 仅对需要 rubric 的数据集启用；Target/Judge 均通过 OpenAI-compatible 协议访问，不把具体供应商写死在评测核心中。

## 6. 架构边界与后续演进

当前系统把 API、Worker、Evaluation Core 和 Artifact Writer 放在同一代码仓库，但运行时已经通过 Redis/PostgreSQL 边界拆分。后续扩展新的评测数据集时，应优先增加 Registry 定义、数据加载器、核心评估/聚合函数和 adapter 分支，再补齐 API catalog、结果 schema、artifact 序列化和测试；不要让前端直接依赖评测核心实现。

Archify showcase 校验已通过 9/9 artifact checks，composition 错误和警告均为 0。`visual-check` 已尝试在桌面尺寸生成截图，但本机 Chrome 进程以 `SIGABRT` 退出，因此截图视觉审阅状态保持 pending，不能据此宣称完成视觉验收。
