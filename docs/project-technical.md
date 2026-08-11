# medical-evals 项目技术文档

## 1. 项目定位

`medical-evals` 是面向医学大语言模型的评测扩展层，建立在 OpenAI Evals
执行引擎之上。仓库只维护医学领域的数据契约、Eval、指标、答案解析器、
Judge 和模型适配器；通用的 CLI、Registry、Recorder 和 CompletionFn 协议由
`pyproject.toml` 中固定 commit 的外部 `evals` 依赖提供。

项目的核心目标是把“数据集定义、模型调用、评分逻辑、运行记录”分开，使同一套
医学评测可以连接 OpenAI-compatible API、代理网关、本地推理服务或其他实现了
CompletionFn 协议的模型服务。

## 2. 总体架构

```text
JSONL 数据集
    │
    ▼
Registry ──► Eval（MedQA / HealthBench）
                  │
                  ├──► CompletionFn ──► 被测模型服务
                  │
                  ├──► Grader / Judge
                  │
                  └──► Recorder ──► JSONL 运行记录与最终报告
```

模型调用边界如下：

```text
medical_evals.evals
        │
        ▼
evals.api.CompletionFn
        │
        ▼
medical_evals.adapters.openai_compatible.OpenAICompatibleCompletionFn
        │
        ▼
OpenAI-compatible /v1/chat/completions endpoint
```

Eval 不直接依赖具体厂商 SDK。`OpenAICompatibleCompletionFn` 负责把字符串、
消息列表或 Evals Prompt 转换为 Chat Completions 请求，并负责重试、响应解析、
采样事件记录和错误记录。

## 3. 目录与职责

```text
medical-evals/
├── medical_evals/
│   ├── adapters/       # 模型服务适配器
│   ├── datasets/       # 数据读取、字段校验和规范化
│   ├── evals/          # 评测任务编排
│   ├── graders/        # 确定性答案解析
│   ├── judges/         # 开放式答案的结构化 Judge
│   ├── metrics/        # 纯评分函数
│   ├── models/         # 模型规格数据结构
│   ├── reports/        # 运行元数据
│   └── human/          # 人工评测扩展预留
├── registry/
│   ├── completion_fns/ # CompletionFn 注册
│   ├── evals/          # Eval 注册和参数
│   └── data/           # 仓库内可复现数据和 smoke 数据
├── configs/            # 运行配置示例和元数据
├── tests/              # 单元、领域和集成测试
├── docs/               # 技术文档、结构说明和设计记录
├── pyproject.toml      # 包元数据、依赖、入口和测试配置
└── uv.lock             # 锁定后的依赖版本
```

`evals/` 不是仓库目录，而是安装依赖后的 Python 包。项目依赖通过 Git URL
固定到 OpenAI Evals 的 commit，以避免上游变更导致评测行为漂移。

## 4. 安装与运行

推荐使用 Python 3.10 或更高版本，并使用 `uv` 管理环境：

```bash
git clone --depth 1 https://github.com/ZCJ0422/medical-evals.git
cd medical-evals
uv sync
uv run pytest -q tests
```

配置 OpenAI-compatible 服务时，至少需要：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://example.com/v1"
export OPENAI_MODEL="your-model"
```

运行外部 Evals CLI 时必须指定项目 Registry：

```bash
uv run oaieval <completion_fn> <eval_id> \
  --registry_path ./registry \
  --local-run \
  --record_path ./experiments/runs/<run>.jsonl \
  --log_to_file ./experiments/runs/<run>.log
```

未指定 `--record_path` 时，外部 Evals 默认把 JSONL 记录写到 `/tmp/evallogs/`，
文件名包含 run ID、CompletionFn 和 Eval 名称。生产或可复现实验应显式指定输出
路径，并保存模型、数据、prompt 和 Judge 配置。

## 5. Registry 机制

Registry 将命令行中的名称映射到 Python 类和运行参数。例如：

```yaml
medical-medqa.dev.v1:
  class: medical_evals.evals.medqa:MedQAEval
  args:
    samples_jsonl: medical_medqa/dev.jsonl
    temperature: 0.1
    max_tokens: 2048
```

`medical-openai-compatible` 的 CompletionFn 注册在
`registry/completion_fns/medical_openai_compatible.yaml`。Eval 注册在
`registry/evals/`。Registry 中的数据路径由外部 Evals 的 Registry 根目录解析，
因此运行命令中的 `--registry_path ./registry` 不应省略。

## 6. 运行链路与记录

一次运行通常经历以下步骤：

1. CLI 读取 CompletionFn 名称、Eval 名称和 Registry 路径。
2. Registry 创建 CompletionFn 和 Eval 实例。
3. Eval 读取并校验 JSONL 数据。
4. Eval 将每条样本转换为模型输入。
5. CompletionFn 调用模型，并把响应转换为 `CompletionResult`。
6. 适配器向 Recorder 写入 sampling 或 error 事件。
7. Eval 写入 match 事件，并返回最终指标。
8. Recorder 将事件和最终报告保存为 JSONL。

所有评分函数都应尽量保持为纯函数。这样可以在不连接模型服务的情况下测试边界，
并将模型调用失败与评分逻辑失败区分开来。

## 7. 版本与复现要求

一次可审计的评测至少应记录：

- Git commit 或代码版本；
- Eval ID 和数据集版本；
- 被测模型名称、服务地址和生成参数；
- prompt 版本；
- Judge 模型及 Judge 生成参数；
- 运行时间、样本数、完成数和失败数；
- 原始 JSONL 记录和日志。

仓库中的 `medical_evals.reports.run_metadata.EvalRunMetadata` 用于保存 Eval ID、
数据集版本、模型规格、prompt 版本和 grader 版本等元数据。API key 不应写入
Registry、配置文件或运行记录。

## 8. 测试策略

```bash
uv run pytest -q tests
```

测试分层如下：

- `tests/medical_evals/`：数据契约、Eval 编排、解析器和报告元数据；
- `tests/metrics/`：MedQA 和 HealthBench 的纯指标；
- `tests/adapters/`：请求转换、响应提取、重试和 Recorder 事件；
- `tests/integration/`：使用 fake client 验证 Registry 到 Eval 的完整链路。

测试使用 fake CompletionFn 或 fake HTTP client，不应因为收集测试而访问真实模型。
缺少真实 API key 时，测试环境可以使用占位值，但真实 API 测试必须单独配置凭据。

## 9. 扩展约束

新增评测时建议遵循以下顺序：

1. 先定义 JSONL 数据契约并为非法输入编写测试；
2. 实现数据加载器和确定性指标；
3. 实现 Eval，只通过 CompletionFn 调用模型；
4. 增加 Registry 配置和最小 smoke 数据；
5. 增加 fake client 的集成测试；
6. 更新对应的专门技术文档和 README 命令。

不要把通用 Evals 源码重新复制到仓库，也不要在模块导入阶段发起网络请求或创建
必须依赖真实凭据的客户端。
