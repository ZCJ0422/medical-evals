# Medical Evals

Medical Evals 用于评测医疗大语言模型，支持 OpenAI-compatible API。可以通过网页工作台管理模型、提交评测、查看结果和下载报告，也可以用命令行运行评测。

目前支持：

- **MedQA**：医疗选择题评测，统计答案准确率、解析成功率等指标。
- **HealthBench**：开放式医疗问答，由 Judge 模型按逐题 rubric 评分。

## 使用网页工作台

需要 Python 3.10+、[uv](https://docs.astral.sh/uv/)、Node.js 20+，以及 PostgreSQL 和 Redis。以下为本地开发启动方式。

### 1. 获取项目并准备数据库

```bash
git clone https://github.com/ZCJ0422/medical-evals.git
cd medical-evals
cp backend/.env.example backend/.env
```

已有 PostgreSQL 和 Redis 时，在 `backend/.env` 中填写连接地址。也可以用 Docker 启动与示例配置匹配的本地服务：

```bash
docker run -d --name medical-evals-postgres -p 127.0.0.1:5432:5432 \
  -e POSTGRES_DB=medical_evals -e POSTGRES_USER=medical_evals \
  -e POSTGRES_PASSWORD=medical_evals \
  -v medical-evals-postgres:/var/lib/postgresql/data postgres:16-alpine

docker run -d --name medical-evals-redis -p 127.0.0.1:6379:6379 redis:7-alpine
```

### 2. 启动 API、Worker 和前端

数据库就绪后，从仓库根目录打开三个终端，分别执行：

**终端一：API**

```bash
cd backend
uv sync
uv run python -m medical_evals_api.cli init-db
uv run python -m medical_evals_api.cli api
```

**终端二：Worker**（完成上一步初始化后启动）

```bash
cd backend
uv run python -m medical_evals_api.cli worker
```

**终端三：前端**

```bash
cd frontend
npm ci
npm run dev
```

### 3. 提交评测

打开 [管理员登录页](http://localhost:3000/admin/login)。本地开发默认账户为 `admin`，密码为 `medical-evals-admin`。

1. 在模型管理页添加模型的 Base URL、模型名称和 API Key。
2. 创建评测，选择数据集、split、目标模型和样本数；HealthBench 还需选择独立的 Judge 模型配置。
3. 提交后由 Worker 执行，在任务列表查看进度，完成后打开结果页查看评分、逐题记录、日志或下载报告。

公众用户可从 [首页](http://localhost:3000) 注册、登录并进入测评空间；管理员可在“测评配置”页设置默认 split、样本数和 Judge 模型。

## 使用命令行

仅运行命令行评测时，不需要启动网页、PostgreSQL 或 Redis。在仓库根目录安装依赖并配置模型：

```bash
uv sync --extra full
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://your-provider.example/v1"
export OPENAI_MODEL="your-model"
mkdir -p experiments/runs
```

运行一题 MedQA：

```bash
uv run oaieval medical-openai-compatible medical-medqa.dev.v1 \
  --registry_path ./registry --max_samples 1 --local-run \
  --record_path ./experiments/runs/medqa-smoke.jsonl
```

运行两题 HealthBench：

```bash
uv run oaieval medical-openai-compatible medical-healthbench.smoke.v1 \
  --registry_path ./registry --max_samples 2 --local-run \
  --record_path ./experiments/runs/healthbench-smoke.jsonl
```

HealthBench 的上述命令默认使用同一套模型配置分别执行回答和 Judge 评分。网页工作台可分别选择目标模型和 Judge 模型。结果写入 `--record_path` 指定的 JSONL 文件。

仓库包含 MedQA 数据和 HealthBench 的小型 smoke 数据。HealthBench 完整数据不随仓库分发，需自行准备并放入 `dataset/HealthBench/`，具体文件名见 [数据集配置](registry/evals/medical_healthbench.yaml)。

## 更多文档

- [API 说明](docs/api.md)
- [架构说明](docs/architecture.md)
- [部署与运维](docs/operations-runbook.md)

默认账户和示例密钥仅用于本地开发；部署前请配置管理员密码、JWT 与加密密钥。API Key 和本地 `.env` 不应提交到 Git。

许可证与来源说明：[LICENSE](LICENSE.md) · [NOTICE](NOTICE.md) · [第三方依赖](THIRD_PARTY_LICENSES.md)。
