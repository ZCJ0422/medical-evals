# Medical Evals 部署与恢复 Runbook

本文面向维护 `medical-evals` 的部署人员。生产环境的凭据、备份密钥和对象存储配置必须由密钥管理系统注入；命令中的连接串均为占位符。

## 1. 组件与数据边界

| 组件 | 持久化内容 | 备份方式 | 恢复优先级 |
| --- | --- | --- | --- |
| PostgreSQL | 用户、模型 profile、评测定义、运行状态、结果和逐样本记录 | `pg_dump`/托管数据库 PITR | 1 |
| Redis | Streams 队列、consumer group、短期限流和 refresh token | Redis RDB/AOF 或托管快照 | 3；队列消息可由运行表 reconcile 重建 |
| artifact volume | `summary.json`、`samples.jsonl`、报告、日志、事件和 manifest | 文件系统快照或对象存储版本 | 2 |
| API/Worker 镜像 | 可从 Git/镜像仓库重建 | 镜像仓库和 Git tag | 4 |

PostgreSQL 是运行状态和结果的事实来源。Redis 丢失后先恢复 API/Worker，再运行队列 reconcile；artifact 缺失时保留数据库结果并将对应运行标记为需要重建报告。

## 2. 发布前检查

1. 确认 `MEDICAL_EVALS_JWT_SECRET`、数据库 URL、Redis URL、artifact 路径和 CORS origin 来自部署密钥，而不是 `.env.example`。
2. 确认 PostgreSQL、Redis、artifact volume 均有最近一次成功备份，并记录备份 ID、时间和校验结果。
3. 暂停滚动发布前的新任务入口，等待正在执行的任务进入终态，或记录需要恢复的运行 ID。
4. 先启动数据库迁移，再启动 API，最后启动 Worker；API/Worker 必须使用同一版本镜像。
5. 验证 `GET /healthz`、`GET /readyz` 和管理员 `GET /api/v1/ops/metrics`。

## 3. PostgreSQL 备份与恢复

### 备份

```bash
export PGHOST=postgres.example.internal PGPORT=5432 PGDATABASE=medical_evals PGUSER=medical_evals
pg_dump --format=custom --file="medical_evals-$(date -u +%Y%m%dT%H%M%SZ).dump" "$PGDATABASE"
sha256sum medical_evals-*.dump
```

保留最近 14 天的每日备份和最近 12 周的每周备份；托管 PostgreSQL 另外开启 PITR，WAL 保留期不少于 7 天。备份文件必须上传到加密、版本化且与数据库故障域分离的存储。

### 恢复

1. 停止 API/Worker 写入，创建隔离数据库并确认目标时间点或 dump 校验和。
2. 恢复到临时数据库，执行完整性检查和只读 smoke 查询：用户数、运行数、结果数，以及最近 10 个运行的状态。
3. 执行应用迁移：`cd backend && uv run alembic upgrade head`。
4. 切换数据库连接或恢复主库，启动 API，再启动 Worker；不要在未验证 artifact 的情况下删除旧数据库。
5. 通过管理指标确认运行状态、过期 lease 和结果可读性；抽样下载一个 `summary.json` 和 `manifest.json`。

## 4. Redis 备份、恢复与队列重建

Redis 只保存短期调度状态。启用托管快照或 RDB/AOF，并至少保留 24 小时。恢复后检查 Streams、consumer group 和 pending 数量：

```bash
redis-cli -u "$MEDICAL_EVALS_REDIS_URL" XINFO STREAM medical-evals:evaluations
redis-cli -u "$MEDICAL_EVALS_REDIS_URL" XINFO GROUPS medical-evals:evaluations
```

如果队列丢失，先保证 PostgreSQL 中的 `queued`/`running` 运行记录完整，再运行项目提供的 reconcile 流程重建未完成任务。恢复后的 Worker 应通过 lease 和幂等键避免重复写入；不要直接手工向 Streams 写入未知 payload。

## 5. Artifact 备份、保留和清理

artifact 根目录必须位于持久化卷；优先同步到版本化对象存储，并保留 `manifest.json` 作为文件清单和 SHA-256 校验依据。建议策略：

- 运行中的任务及最近 30 天的终态运行：保留全部 artifact；
- 30–180 天：转低频存储，仍保留 summary、manifest 和事件日志；
- 超过 180 天：删除大体积样本和报告，只保留数据库摘要、manifest 和审计事件；
- 任何删除都先生成 dry-run 清单，按 `run_id` 排除运行中任务、法务保留和最近失败运行。

清理后抽样核对数据库结果与 manifest；发现校验失败时停止后续删除并恢复最近一次卷快照。删除前后记录文件数量、字节数和操作人，便于与 `/api/v1/ops/metrics` 对账。

## 6. 故障处置顺序

1. 读取 `/api/v1/ops/metrics`：先看队列错误、pending、过期 lease 和失败类别。
2. API 不可用时检查 `/healthz`、应用日志和数据库连接池；数据库不可用时进入只读保护，不清理 Redis 或 artifact。
3. Worker 不消费时检查 Redis consumer group、pending 消息、lease heartbeat 和 Worker 日志；必要时只重启 Worker。
4. 结果存在但报告下载失败时校验 artifact volume 和 `manifest.json`，优先从对象存储恢复单个运行目录。
5. 任何恢复操作完成后，执行一个 1–2 样本的 MedQA smoke，确认入队、消费、结果、事件和下载链路闭环。

## 7. 演练记录

每季度至少演练一次 PostgreSQL + artifact 联合恢复，并记录：备份 ID、目标时间点、RPO、RTO、迁移版本、恢复的运行 ID、校验结果和遗留问题。演练输出应存放在受控文档库，不把真实凭据或用户数据提交到 Git。
