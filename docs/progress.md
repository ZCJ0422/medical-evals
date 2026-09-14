# Medical Evals 当前进度与待办

更新时间：2026-09-14

本文以当前 `main` 工作区和代码为准；功能状态来自仓库实现、测试目录和最近提交，不把未验证的设想标记为已完成。

## 当前进度

### 已完成的主链路

- [x] 建立 `medical_evals` 医疗评测核心，支持 MedQA 和 HealthBench 的数据加载、模型请求、重试、解析、逐样本评分和聚合指标。
- [x] 提供 OpenAI-compatible CompletionFn/客户端边界，CLI 与 Workbench 共用评测核心，同时保留各自的调度、Recorder、队列和 artifact 编排。
- [x] 实现 FastAPI 后端、Next.js 前端和独立 Worker；后端包含认证、模型 profile、数据集目录、测评运行、结果、报告和健康检查接口。
- [x] 完成多用户认证和权限隔离：JWT access token、refresh token 轮换、管理员工作台、普通用户公众门户和运行 ownership 过滤。
- [x] 完成 PostgreSQL + Redis Streams 生产型执行路径；包含 consumer group、任务去重、Worker lease、heartbeat、pending message reclaim 和 reconcile 恢复。
- [x] 完成测评 artifact 体系：metadata、summary、samples、日志、checkpoint、HTML report，以及数据库中的运行结果和逐样本结果。
- [x] 完成 HealthBench 双模型路径：Target 模型生成回答，Judge 模型执行 rubric 评分；结果页可展示总分、逐条 Rubric 和低分样本。
- [x] 完成管理员测评配置页：可设置默认 split、默认样本量和 Judge profile；公众端提交时自动采用这些默认值。
- [x] 完成模型连接安全边界：API key 加密存储、公开 Base URL 校验、请求错误清理和连接测试限流。
- [x] 补齐架构、数据库和 API 设计文档；架构图规格已通过 Archify showcase 校验。

### 当前实现基线

- 主工作区分支：`main`。
- 本次代码整理提交：后端 `1b84cf4`，前端和浏览器回归 `577918d`；同时保留此前的共享评测配置提交 `4163ef0`。
- 本地三个功能 worktree 未纳入本次整理，其合并状态未在本次核实。
- 架构图保留 `4163ef0` 时点的代码证据，不能作为新增监控和目录实现的逐项证明；旧的浏览器检查失败诊断已移出发布内容，本次未重新进行架构图视觉验收。

### 验证状态

2026-09-14，本地验证结果：

| 检查 | 命令（仓库根目录，除另有说明） | 结果 |
| --- | --- | --- |
| 核心 Python 测试 | `OPENAI_API_KEY=sk-test .venv/bin/python -m pytest -q tests` | 102 passed |
| 后端测试 | `PYTHONPATH=.:backend OPENAI_API_KEY=sk-test backend/.venv/bin/python -m pytest -q backend/tests` | 174 passed、3 skipped |
| Python 类型检查 | `MYPYPATH=backend .venv/bin/mypy --config-file=mypy.ini --no-site-packages .` | 142 个源文件通过 |
| 前端类型检查 | `cd frontend && npm run typecheck` | 通过 |
| 前端生产构建 | `cd frontend && npm run build` | 通过 |
| 浏览器回归 | `cd frontend && npm run test:e2e -- --reporter=line` | 10 passed |
| 补丁格式 | `git diff --check` | 通过 |

本地根目录与 backend 使用各自已有虚拟环境；不是一次重新安装依赖的全新环境验证。浏览器测试使用每次独立的临时 SQLite 数据库、artifact 目录，以及 `3107` / `8107` 专用端口，不复用开发服务；模型执行使用 dry-run fixture，Redis 设置为不可用以验证数据库排队降级路径。

3 项跳过项分别需要真实 PostgreSQL、Redis 或二者联合环境，依赖 `MEDICAL_EVALS_TEST_POSTGRES_URL` / `MEDICAL_EVALS_TEST_REDIS_URL`。本次未执行真实外部模型请求，也未验证生产部署。

本次修复覆盖：空库迁移外键约束、split ID 在不同定义之间的隔离、HealthBench 默认 smoke 顺序、配置校验异常、运行完成后 artifact 清单的完整性、报告下载和日志展示。类型检查还修复了 Worker 对两类 repository 的类型声明，以及旧 SQLite lease 恢复返回计数时的兼容处理。

## 待办事项

### P0：部署前必须完成

- [x] 完成本次核心/后端测试、前端类型检查和生产构建、浏览器回归。
- [ ] 在 CI 全新安装依赖的环境执行相同验证。
- [ ] 补齐共享配置与公众提交路径的浏览器回归，包括默认 split、样本上限、Judge 必填、重复模型名称和用户隔离的完整组合。
- [ ] 在实际 PostgreSQL、Redis 和外部 OpenAI-compatible endpoint 上跑小样本 MedQA 与 HealthBench smoke，核对队列、artifact、结果页和报告下载。
- [ ] 确认生产环境的 JWT secret、数据库密码、Redis 地址、artifact volume 和 CORS origin 使用部署配置。

Git 发布时通过代理推送 `main`，随后比较 `git rev-parse HEAD` 与 `git ls-remote origin refs/heads/main`；实时同步状态以 Git 查询为准，不在文档中固定记录 ahead/behind。

### P1：近期工程完善

- [x] 为 dataset definition、split、版本、样本数和 rubric 建立可审计的数据库目录；新增 `evaluation_definition_splits` 表、Alembic `0003_dataset_catalog` 迁移、源文件 SHA-256 指纹和数据库驱动的 v1 catalog API。
- [x] 增加结果 schema、artifact schema 和运行事件的版本迁移策略：结果使用 `workbench.result.v2`，artifact 使用 `manifest.json` 的 `workbench.artifacts.v1`，事件使用 `events.jsonl` 的 `workbench.event.v1`，并保留旧结果读取默认值。
- [x] 增加后台运行监控：新增管理员 `GET /api/v1/ops/metrics`，聚合队列深度/pending、lease 超时、失败类别、请求成功数、解析成功率和 artifact 文件/字节占用，并在管理员概览页展示；覆盖 Redis 不可用时的降级行为。
- [x] 将 API、Worker、Redis、PostgreSQL 和 artifact volume 的备份、恢复、保留期和清理策略写成部署 runbook，见 `docs/operations-runbook.md`。
- [x] 完善前端的错误恢复、长任务刷新、取消/重试反馈、无障碍检查：运行列表持续轮询并在页面恢复可见时刷新，结果页错误可直接重试，取消/重试显示反馈，进度条/状态/弹窗保留语义化 ARIA，新增中英文重试文案；前端 `npm run typecheck` 通过。
- [x] 对外部模型响应解析、超时、限流、部分失败和 Judge 输出异常增加供应商兼容性测试矩阵；覆盖 dict/SDK object/content parts/legacy text 响应、可重试错误和 malformed rubric JSON，相关测试 39 项通过。

### P2：产品与研究扩展

- [ ] 接入更多 provider SDK、原生推理服务、模型网关和 Agent/RAG/tool-using 系统，继续通过 CompletionFn/adapter 隔离供应商差异。
- [ ] 增加专家人工评测、生产模型评测、排行榜和可复现的公开评测快照。
- [ ] 增加实验配置、运行快照和模型版本的可视化比较；保留当前 `experiments/` 目录与 Registry 的版本化约束。
- [ ] 评估多 Worker、多机部署下的扩展策略，包括 Redis 高可用、PostgreSQL 连接池、artifact 对象存储和任务优先级。

## 状态约定

`[x]` 表示代码和文档中已有实现证据；`[ ]` 表示尚未完成，或虽有部分实现但还缺少当前版本的验证证据。每次发布前应更新更新时间、HEAD、验证命令结果和仍未关闭的 P0/P1 项。
