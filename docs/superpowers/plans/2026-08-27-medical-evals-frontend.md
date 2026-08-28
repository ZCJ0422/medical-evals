# Medical Evals 前端开发计划

## 1. 背景与目标

当前 `main` 已具备多用户后端能力，包括注册登录、权限隔离、模型配置、MedQA/HealthBench 评测、PostgreSQL 持久化、Redis 队列和 Worker。

前端当前仍主要使用旧版管理员接口，例如 `/api/evaluations` 和 `/api/datasets`，而新版后端的多用户接口统一使用 `/api/v1` 前缀。因此前端开发的第一目标不是单纯增加页面，而是先完成前端 API 层和数据模型向新版后端的迁移。

目标是实现以下完整闭环：

```text
注册 → 登录 → 配置模型 → 选择数据集 → 创建评测
→ 查看队列和运行状态 → 查看结果 → 取消/重试
```

## 2. 当前前端与后端的主要差异

### 2.1 接口前缀差异

当前前端主要调用：

- `/api/auth/login`
- `/api/evaluations`
- `/api/datasets`

目标接口为：

- `/api/v1/auth/register`
- `/api/v1/auth/login`
- `/api/v1/auth/refresh`
- `/api/v1/auth/logout`
- `/api/v1/me`
- `/api/v1/models`
- `/api/v1/datasets`
- `/api/v1/evaluations`
- `/api/v1/evaluations/{run_id}/summary`
- `/api/v1/evaluations/{run_id}/samples`

### 2.2 模型配置方式差异

当前前端在创建评测时直接提交：

- 模型名称
- Base URL
- API Key

目标流程是：

1. 用户先创建模型配置
2. 后端加密保存 API Key
3. 前端创建评测时只提交模型配置 ID

前端不应在创建评测时再次提交 API Key。

### 2.3 资源模型差异

旧版前端使用 `task_id`，新版后端使用 `run_id`。

前端类型、路由参数、结果查询和任务操作需要统一到 `run_id`。

## 3. 第一阶段：统一前端 API 层

### 目标

建立统一、类型安全、可处理新版错误结构的 API 客户端。

### 修改文件

- `frontend/lib/api.ts`
- `frontend/lib/auth.ts`
- `frontend/lib/types.ts`

### 主要工作

- 统一设置 API Base URL
- 统一附加 Authorization
- 统一处理 JSON、Blob 和文本响应
- 统一处理 `401`、`403`、`404`、`409`、`422` 和 `500`
- 解析新版错误结构：

```json
{
  "error": {
    "code": "invalid_request",
    "message": "具体错误",
    "request_id": "..."
  }
}
```

- 在用户提示中保留必要的 request ID
- 不向用户展示内部堆栈或 API Key
- 处理 access token 失效
- 为后续 refresh token 轮换预留接口

### 建议类型

```ts
type User = {
  username: string
  role: "user" | "admin"
  status: string
}

type TokenResponse = {
  access_token: string
  refresh_token: string
  user: User
}
```

### 验收标准

- 所有新页面默认使用 `/api/v1`
- API 错误能够转换成用户可读文本
- token 失效后能自动清理本地会话并跳转登录页
- API Key 不出现在 URL、错误提示和日志中

## 4. 第二阶段：注册、登录和会话管理

### 页面

- `/login`
- `/register`

### 注册流程

```text
提交用户名和密码
    ↓
POST /api/v1/auth/register
    ↓
保存 access_token 和 refresh_token
    ↓
进入 /app
```

### 登录流程

```text
提交用户名和密码
    ↓
POST /api/v1/auth/login
    ↓
保存 token
    ↓
GET /api/v1/me
    ↓
进入 /app
```

### AppShell 改造

当前 `AppShell` 只通过 `hasToken()` 判断会话，需要改成：

- 检查 token 是否存在
- 请求 `/api/v1/me`
- 显示当前用户名和角色
- token 无效时自动退出
- 退出时调用 `/api/v1/auth/logout`
- 防止未登录用户访问 `/app/*`

### 测试

- 未登录访问 `/app` 跳转 `/login`
- 登录成功进入工作台
- 注册成功进入工作台
- 重复用户名显示错误
- 错误密码显示通用错误
- token 失效后自动退出

## 5. 第三阶段：模型配置页面

### 页面

```text
/app/models
/app/models/new
/app/models/[id]/edit
```

### 页面功能

模型列表显示：

- 模型配置名称
- Base URL
- Model Name
- 是否已配置 API Key
- 创建时间
- 编辑
- 删除
- 测试连接

模型表单字段：

- Name
- Base URL
- Model Name
- API Key

### API

```text
GET    /api/v1/models
POST   /api/v1/models
GET    /api/v1/models/{id}
PATCH  /api/v1/models/{id}
DELETE /api/v1/models/{id}
POST   /api/v1/models/{id}/test
```

### 安全要求

前端不能：

- 将 API Key 写入 localStorage
- 将 API Key 写入 URL
- 在模型列表回显 API Key
- 在错误信息中展示 API Key
- 在长期全局状态中缓存 API Key

推荐流程：

```text
表单输入 → POST/PATCH → 清空表单 → 只显示 has_api_key
```

## 6. 第四阶段：迁移新建评测流程

### 页面

继续使用：

```text
/app/evaluations/new
```

但重构 `EvaluationWizard`，不再让用户在新建评测时直接填写模型 API Key。

### 步骤一：选择数据集

调用：

```text
GET /api/v1/datasets
```

仅展示系统内置的：

- MedQA
- HealthBench

根据数据集自动确定：

- 是否需要 Judge Model
- 可用 split
- 默认样本数
- rubric 配置

### 步骤二：选择目标模型

调用：

```text
GET /api/v1/models
```

用户从自己的模型配置中选择目标模型。

如果没有模型配置：

- 显示空状态
- 提供“配置模型”按钮
- 跳转 `/app/models/new`

### 步骤三：选择 Judge 模型

只有 HealthBench 显示该步骤。

要求：

- Judge 模型必须属于当前用户
- Judge 模型不能与目标模型相同
- Judge 模型配置必须包含有效 API Key

### 步骤四：运行参数

- 任务名称
- split
- sample limit
- 评测配置

### 步骤五：预览和创建

创建请求示例：

```json
{
  "name": "MedQA smoke",
  "evaluation_definition_id": "medqa",
  "target_model_id": "model-profile-id",
  "judge_model_id": null,
  "split": "dev",
  "sample_limit": 10,
  "config": {}
}
```

调用：

```text
POST /api/v1/evaluations
```

前端不再调用旧版 preflight 和旧版任务创建接口。

## 7. 第五阶段：评测任务列表

### 页面

```text
/app/evaluations
```

### API

```text
GET    /api/v1/evaluations
GET    /api/v1/evaluations/{run_id}
POST   /api/v1/evaluations/{run_id}/cancel
POST   /api/v1/evaluations/{run_id}/retry
DELETE /api/v1/evaluations/{run_id}
```

### 前端类型

```ts
type EvaluationRun = {
  run_id: string
  name: string
  evaluation_definition_id: string
  target_model_id: string
  judge_model_id: string | null
  dataset_version_id: string
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled"
  progress: EvaluationProgress
}
```

### 功能

- 状态筛选
- 名称搜索
- 数据集筛选
- 分页
- 自动刷新
- 取消任务
- 重试任务
- 删除任务
- 查看结果

### 轮询策略

- `queued` / `running`：约 3 秒轮询
- `succeeded` / `failed` / `cancelled`：停止轮询
- 页面不可见时降低轮询频率
- 页面重新激活时立即刷新

## 8. 第六阶段：评测结果页面

### 页面

```text
/app/evaluations/[run_id]/results
```

### API

```text
GET /api/v1/evaluations/{run_id}/summary
GET /api/v1/evaluations/{run_id}/samples
```

### 页面内容

#### 运行摘要

- 任务名称
- 数据集
- 目标模型
- Judge 模型
- 当前状态
- 创建时间
- 完成时间

#### 质量指标

- 总分
- Accuracy
- Parse success rate
- Request success rate
- Failed samples
- Retry count

#### HealthBench 指标

- Rubric 总分
- 各维度得分
- 低分比例
- Judge failure rate
- Error categories

#### 样本列表

- 样本编号
- 样本 ID
- 模型原始回答
- 得分
- 错误信息
- Judge 评价
- 分页加载

#### 日志

确认新版结果 API 是否提供日志接口；如果没有，前端应将日志展示能力限定在当前后端已支持的接口范围内。

## 9. 第七阶段：统一加载、错误和空状态

### 加载状态

- 页面 skeleton
- 按钮 loading
- 防止重复提交
- 防止重复删除、取消和重试

### 空状态

- 没有模型配置
- 没有评测任务
- 没有结果样本
- 没有运行日志

### 错误状态

统一显示：

- 用户可理解的错误信息
- 必要时显示 request ID
- 重试按钮
- 不显示内部堆栈
- 不显示 API Key

### HTTP 状态处理

| 状态 | 前端行为 |
|---|---|
| 401 | 清理会话并跳转登录 |
| 403 | 显示无权限提示 |
| 404 | 显示资源不存在 |
| 409 | 显示状态冲突，例如运行中任务不能删除 |
| 422 | 显示字段或表单错误 |
| 500 | 显示通用错误并提供重试 |

## 10. 第八阶段：导航和页面结构

建议的工作台导航：

```text
Medical Evals
├── 概览
├── 模型配置
├── 测评任务
└── 当前用户
    ├── 账户信息
    └── 退出登录
```

建议路由：

```text
/
├── /login
├── /register
└── /app
    ├── /models
    ├── /models/new
    ├── /models/[id]/edit
    ├── /evaluations
    ├── /evaluations/new
    └── /evaluations/[run_id]/results
```

## 11. 第九阶段：前后端联调

### 最小闭环

```text
注册
  ↓
登录
  ↓
创建模型配置
  ↓
测试模型连接
  ↓
选择 MedQA
  ↓
创建 1 个样本的评测
  ↓
查看任务状态
  ↓
Worker 执行
  ↓
查看结果
```

### 权限闭环

```text
Alice 创建模型和评测
  ↓
Bob 登录
  ↓
Bob 看不到 Alice 的模型
  ↓
Bob 看不到 Alice 的评测
  ↓
Bob 无法访问 Alice 的结果
```

### 任务控制闭环

```text
创建任务
  ↓
取消任务
  ↓
创建 retry
  ↓
检查 retry_of_run_id
```

## 12. 第十阶段：测试与交付标准

### TypeScript 和构建

```bash
cd frontend
npm run typecheck
npm run build
```

### 后端联调

```bash
cd backend
uv run pytest -q
```

### Playwright

新增或调整以下测试：

- 登录测试
- 注册测试
- 模型配置测试
- 模型连接测试
- MedQA 创建测试
- HealthBench Judge 配置测试
- 任务状态刷新测试
- 取消和重试测试
- 结果展示测试
- 跨用户隔离测试
- API 错误展示测试

### 交付标准

- 用户可以注册和登录
- 用户可以配置自己的模型 API
- 用户可以选择 MedQA 或 HealthBench
- 用户可以创建评测
- Worker 状态可以被前端看到
- 用户可以查看自己的结果
- 用户无法访问其他用户资源
- API Key 不会出现在页面、URL、日志和错误提示中
- `npm run typecheck` 通过
- `npm run build` 通过
- Playwright 核心流程通过

## 13. 推荐提交拆分

建议拆成以下五个提交：

```text
1. feat: align frontend api client with v1 backend
2. feat: add user registration and session management
3. feat: add user-owned model profile management
4. feat: migrate evaluation wizard and list to v1 APIs
5. feat: integrate evaluation results and end-to-end tests
```

## 14. 实施顺序

优先完成：

1. API 客户端和类型迁移
2. 注册、登录和会话管理
3. 模型配置页面

完成后形成第一个可用闭环：

```text
注册 → 登录 → 配置模型
```

随后再实现评测创建、任务管理和结果展示。
