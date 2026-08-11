# medical-evals 项目结构与维护说明

本文档说明 `medical-evals` 的目录职责、评测执行链路、数据与 Registry 的关系、测试组织方式，以及哪些文件属于可再生的本地生成物。

## 1. 项目定位

`medical-evals` 是构建在 OpenAI Evals 执行引擎之上的医学大模型评测扩展层。项目当前同时包含：

1. 保留的通用 Evals 执行引擎，用于调度、模型调用、Recorder、Registry 和 CLI；
2. 医学领域扩展，用于 MedQA、HealthBench、医学数据加载、医学指标和 rubric Judge；
3. Registry 配置、测试、运行记录和设计文档。

核心边界如下：

```text
评测任务（Eval）
    ↓
CompletionFn
    ↓
OpenAI-compatible API / OpenAI API / 本地服务 / Agent 适配器
```

评测任务不应直接调用具体模型厂商 SDK。所有模型调用都应通过 `CompletionFn` 完成，这样同一个评测可以复用不同的模型、网关或本地推理服务。

## 2. 顶层目录

```text
medical-evals/
├── evals/                    # 通用 Evals 执行引擎
├── medical_evals/            # 医学领域扩展层
├── evals/registry/           # 当前 CLI 使用的 Registry
├── registry/                 # 医学领域 Registry 的预留目录
├── tests/                    # 单元、集成和领域测试
├── docs/                     # 使用文档、设计文档和实现计划
├── configs/                  # 可复用的运行配置示例
├── experiments/              # 运行配置、运行记录和快照目录
├── examples/                 # 通用 Evals 示例 Notebook
├── scripts/                  # Evals 生成器和运维脚本
├── .github/                 # CI、Issue 模板和工作流
├── pyproject.toml            # Python 包、依赖、CLI 和 pytest 配置
├── uv.lock                  # 依赖锁定文件
├── Makefile                 # 常用开发命令
└── README.md                # 项目入口说明
```

## 3. 核心源码目录

### 3.1 `evals/`：通用执行引擎

这是项目依赖的通用评测运行时，保留 OpenAI Evals 的主要抽象。它不是医学业务代码，但医学评测依赖它的执行能力。

```text
evals/
├── api.py                   # CompletionFn、CompletionResult 等协议
├── base.py                  # RunSpec、EvalSpec 等基础数据结构
├── data.py                  # JSONL 和通用数据读取
├── eval.py                  # Eval 基类、样本调度和并发执行
├── record.py                # Recorder、Event 和记录辅助函数
├── registry.py              # Registry 解析、类加载和 CompletionFn 创建
├── metrics.py               # 通用指标
├── cli/
│   ├── oaieval.py           # 单个 Eval 的 CLI
│   └── oaievalset.py        # Eval set 的 CLI
├── completion_fns/          # 通用 CompletionFn 实现
├── solvers/                 # Solver 抽象及供应商实现
├── prompt/                  # Prompt 类型和格式化
├── utils/                   # 通用工具
└── elsuite/                 # 保留的通用评测任务集合
```

`evals/elsuite/` 包含大量原有通用任务，例如基础匹配、翻译、模型分级、工具调用和对话任务。这些任务不是医学评测，但属于保留的通用执行引擎内容；除非明确决定不再兼容通用 Evals，否则不应随意删除。

### 3.2 `medical_evals/`：医学评测扩展

```text
medical_evals/
├── adapters/
│   └── openai_compatible.py  # OpenAI-compatible Chat API 适配器
├── datasets/
│   ├── medqa.py              # MedQA JSONL 校验与读取
│   └── healthbench.py        # HealthBench JSONL 校验与读取
├── evals/
│   ├── medqa.py              # MedQA 选择题评测
│   └── healthbench.py        # HealthBench 开放式问答评测
├── graders/
│   └── choice_parser.py      # 选择题答案解析
├── judges/
│   └── rubric.py             # HealthBench rubric Judge 和 JSON 解析
├── metrics/
│   ├── medical_qa.py         # 选择题 accuracy、解析成功率
│   └── healthbench.py        # rubric 加权、总体和 tag 评分
├── models/
│   └── model_spec.py         # 模型规格数据结构
├── reports/
│   └── run_metadata.py       # 运行元数据
└── human/                    # 人工评测扩展预留
```

医学层的推荐职责边界：

- `datasets/` 只负责读取、校验和规范化数据，不调用模型；
- `evals/` 负责把数据、CompletionFn、Judge 和 Recorder 串起来；
- `metrics/` 只负责纯计算，不发起网络请求；
- `judges/` 负责评分模型的输入输出协议和结构化结果解析；
- `adapters/` 负责具体模型服务的调用、重试和 sampling 记录。

## 4. 当前已支持的评测

### 4.1 MedQA 选择题

主要文件：

- `medical_evals/datasets/medqa.py`
- `medical_evals/evals/medqa.py`
- `medical_evals/graders/choice_parser.py`
- `medical_evals/metrics/medical_qa.py`
- `evals/registry/evals/medical_medqa.yaml`

流程：

```text
MedQA JSONL
    ↓
读取题目、四个选项和标准答案
    ↓
模型只收到题目与选项
    ↓
解析 A/B/C/D
    ↓
accuracy + parse_success_rate
```

Registry ID：`medical-medqa.dev.v1`。

### 4.2 HealthBench 开放式问答

主要文件：

- `medical_evals/datasets/healthbench.py`
- `medical_evals/evals/healthbench.py`
- `medical_evals/judges/rubric.py`
- `medical_evals/metrics/healthbench.py`
- `evals/registry/evals/medical_healthbench.yaml`
- `evals/registry/data/medical_healthbench/smoke.jsonl`

流程：

```text
HealthBench prompt
    ↓
目标模型生成自然语言回答
    ↓
Judge 逐条读取 prompt、候选回答和 rubric criterion
    ↓
返回 criteria_met + explanation
    ↓
计算单题加权分数、overall_score 和 tag_scores
```

目标模型不会收到 rubric。单题评分公式为：

```text
achieved = Σ(points_i)，仅累加 criteria_met=true 的标准
positive_max = Σ(points_i)，仅累加 points_i > 0 的标准
sample_score = achieved / positive_max
```

负分 rubric 用于惩罚危险行为，但不进入分母。总体分数和 tag 分数会裁剪到 `[0, 1]`。

Registry ID：

- `medical-healthbench.smoke.v1`
- `medical-healthbench.oss.v1`
- `medical-healthbench.hard.v1`
- `medical-healthbench.consensus.v1`

完整 HealthBench 数据位于工作区外层的：

```text
../dataset/HealthBench/
```

Registry 中的完整数据路径通过相对路径引用；smoke 数据则保留两条小样本，以便在不运行完整数据的情况下验证模型、Judge、Recorder 和 Registry 的连通性。

## 5. Registry 结构

当前真正被 CLI 使用的是：

```text
evals/registry/
├── completion_fns/            # CompletionFn 注册
├── data/                      # 注册数据和 smoke 数据
├── evals/                     # Eval 与 Eval set 定义
├── eval_sets/                 # 多个 Eval 的组合
├── modelgraded/               # 通用 model-graded 配置
└── solvers/                   # Solver 注册
```

医学评测配置位于 `evals/registry/evals/`，例如：

- `medical_medqa.yaml`
- `medical_healthbench.yaml`

根目录的 `registry/` 目前只有目录占位文件，是未来医学领域独立 Registry 层的预留位置。不要把当前可运行的 YAML 配置误放到该目录，除非同时修改 Registry 加载逻辑。

## 6. 数据与运行产物

### 6.1 版本化数据

适合纳入仓库的数据包括：

- 小型 smoke 数据；
- 可公开、可复现、体积可接受的评测样本；
- 与 Registry ID 一一对应的数据版本。

HealthBench 完整数据当前由工作区根目录的 `dataset/HealthBench/` 提供，`medical-evals` 只保存 Registry 引用和 smoke 样本。

### 6.2 运行结果

`experiments/` 用于保存实验配置、运行记录和快照：

```text
experiments/
├── configs/                  # 实验配置
├── runs/                     # 本地运行输出
└── snapshots/                # 数据或配置快照
```

模型输出和日志默认不纳入 Git，相关规则位于 `.gitignore`。这些文件可能包含大量回答、提示词或敏感信息，应按实验需要保留、归档或清理。

## 7. 测试目录

```text
tests/
├── adapters/                 # API 适配器测试
├── evals/                    # 通用 Eval 相关测试
├── integration/              # 端到端流水线测试
├── medical_evals/            # 医学数据、Eval、解析器和元数据测试
├── metrics/                  # 医学指标测试
└── unit/                     # 通用单元测试
```

HealthBench 相关测试包括：

- `tests/medical_evals/test_healthbench_dataset.py`：字段校验和规范化；
- `tests/metrics/test_healthbench.py`：正负分、分母和 tag 聚合；
- `tests/medical_evals/test_healthbench_judge.py`：Judge JSON 解析和调用参数；
- `tests/medical_evals/test_healthbench_eval.py`：rubric 不泄露和 Eval 编排；
- `tests/integration/test_healthbench_pipeline.py`：Registry、目标模型和 Judge 的 smoke 流程。

推荐验证命令：

```bash
cd medical-evals
OPENAI_API_KEY=dummy EVALS_SEQUENTIAL=1 \
pytest -q tests/medical_evals tests/adapters tests/integration
```

如需运行不依赖真实模型服务的本地测试，不要把虚假的 API key 传给会根据环境变量决定是否执行外部测试的旧测试；优先运行明确的测试子目录，或按测试文件筛选。

## 8. 文档与开发记录

```text
docs/
├── run-evals.md              # CLI 运行方式
├── completion-fns.md         # CompletionFn 说明
├── completion-fn-protocol.md # CompletionFn 协议
├── custom-eval.md            # 自定义 Eval
├── build-eval.md             # 构建 Eval
└── superpowers/
    ├── specs/                # 已确认的设计规格
    └── plans/                # 实现计划
```

当前医学功能的设计和实现记录包括：

- HealthBench 开放式问答设计规格；
- HealthBench 实现计划；
- MedQA 相关设计和参数配置计划。

这些文档属于项目决策记录，不是运行时依赖，除非内容已经过时或与代码矛盾，否则不应作为“无用文件”删除。

## 9. 可清理文件策略

以下文件属于可再生生成物，不应提交到 Git：

```text
build/
dist/
.pytest_cache/
.mypy_cache/
.ruff_cache/
__pycache__/
*.pyc
*.egg-info/
._*
.DS_Store
```

本次清理已移除：

- `build/` 构建目录；
- `.pytest_cache/`；
- `medical_evals.egg-info/`；
- 源码、测试和文档目录中的 `__pycache__`；
- 项目目录中的 macOS `._*` 和 `.DS_Store` 元数据。

`.venv/` 暂时保留，因为它是本地开发环境。它已被 `.gitignore` 忽略，不属于交付源码；如果需要完全重建环境，可以在确认不再依赖当前环境后删除并通过 `uv sync` 重建。

## 10. 推荐开发流程

1. 在 `medical_evals/datasets/` 中定义并测试数据契约；
2. 在 `medical_evals/metrics/` 中先实现纯指标和边界测试；
3. 在 `medical_evals/judges/` 中定义外部 Judge 的结构化协议；
4. 在 `medical_evals/evals/` 中编排模型、Judge 和 Recorder；
5. 在 `evals/registry/evals/` 注册可运行 ID；
6. 为每个新 Eval 添加单元测试和 smoke 集成测试；
7. 更新 `README.md` 或 `docs/run-evals.md`；
8. 删除构建缓存和本地输出前，确认它们不包含需要归档的实验结果；
9. 使用 `git diff --check` 和目标测试集完成交付前验证。

## 11. 当前维护边界

### 应继续保留

- `evals/` 通用执行引擎，因为医学层依赖它；
- `medical_evals/` 医学评测实现；
- `evals/registry/` 当前运行配置；
- `tests/` 与现有评测对应的测试；
- `docs/` 中仍与当前架构一致的设计和运行文档；
- `examples/` 中用于理解通用 Evals 接口的示例。

### 不应直接提交

- 本地构建目录；
- Python 缓存和打包元数据；
- macOS 资源分叉文件；
- 未经审查的模型回答和日志；
- 包含 API key、cookie 或本地认证状态的文件。

### 后续可单独评估

- 是否仍需保留全部 `evals/elsuite/` 通用任务；
- 是否将通用 Evals 引擎拆成独立依赖，而不是继续放在仓库中；
- 是否归档 `examples/` 中与医学评测无关的 Notebook；
- 是否把完整 HealthBench 数据纳入独立数据版本管理，而不是通过工作区相对路径引用。

这些事项会改变项目边界或复现方式，不应在一次普通清理中直接删除。
