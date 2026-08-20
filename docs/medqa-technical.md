# MedQA 技术文档

## 1. 评测目标

MedQA 在本项目中实现为四选一医学知识问答评测。模型只看到题目和 A/B/C/D
四个选项，输出应为一个选项字母。评测器解析模型输出后，与数据中的标准答案
比较，计算准确率和解析成功率。

对应的 Registry ID 是：

```text
medical-medqa.dev.v1
```

核心实现文件：

- `medical_evals/datasets/medqa.py`：读取和校验样本；
- `medical_evals/evals/medqa.py`：构造 prompt、调用模型和记录 match；
- `medical_evals/graders/choice_parser.py`：从模型输出解析选项；
- `medical_evals/metrics/medical_qa.py`：计算指标；
- `registry/evals/medical_medqa.yaml`：注册 Eval 和默认参数；
- `registry/data/medical_medqa/dev.jsonl`：开发集数据。

## 2. 数据格式

每行是一个 JSON 对象，必须包含 `question`、`options` 和 `answer`：

```json
{
  "question": "关于某疾病的描述，以下哪项正确？",
  "options": {
    "A": "选项一",
    "B": "选项二",
    "C": "选项三",
    "D": "选项四"
  },
  "answer": "C"
}
```

数据加载器的约束：

- 每行必须是 JSON object；
- `question` 必须是非空字符串；
- `options` 必须恰好包含 `A`、`B`、`C`、`D`；
- 四个选项必须是字符串；
- `answer` 必须是 A、B、C、D 之一；
- 空行会被跳过；
- 答案字母会被规范化为大写。

非法 JSON 或字段不符合契约时，加载器会报告行号并抛出 `ValueError`，避免静默
丢题或使用错误答案。

## 3. Prompt 和模型输出

`build_prompt` 将每条样本构造成中文单项选择题提示。标准答案不会放入 prompt，
并要求模型只输出一个字母：

```text
请回答下面的医学单项选择题。
题目：...
选项：
A. ...
B. ...
C. ...
D. ...
要求：
不要输出解释、推理过程、答案文字、标点符号、Markdown 或其他内容。
请只输出一个选项字母（A、B、C 或 D）。
```

实际请求通过 `CompletionFn` 发送，Eval 不直接调用 OpenAI SDK。Registry 默认
生成参数为：

```yaml
temperature: 0.1
max_tokens: 2048
```

可以在 CLI 中覆盖：

```bash
--extra_eval_params temperature=0.2,max_tokens=512
```

## 4. 答案解析和评分

答案解析由 `medical_evals.graders.choice_parser.parse_choice` 完成。解析结果为
`A`、`B`、`C`、`D` 或 `None`。Eval 为每道题记录一个 match 事件，主要字段包括：

```json
{
  "expected": "C",
  "picked": "C",
  "sampled": "C",
  "correct": true,
  "options": ["A", "B", "C", "D"]
}
```

指标定义：

```text
accuracy = 正确题数 / match 事件数
parse_success_rate = 成功解析出选项的题数 / 请求成功的题数
```

没有样本时 `accuracy` 返回 `0.0`。当没有任何请求成功（包括空数据集或所有
请求都失败）时，`parse_success_rate` 没有可用分母，返回 `None`（JSON API 中为
`null`）。无法解析的回答会降低 `parse_success_rate`，且不会被视为正确答案。

## 5. 运行方式

浅克隆并安装：

```bash
git clone --depth 1 https://github.com/ZCJ0422/medical-evals.git
cd medical-evals
uv sync
```

配置模型服务：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://example.com/v1"
export OPENAI_MODEL="your-model"
```

运行一个样本进行连通性检查：

```bash
uv run oaieval medical-openai-compatible medical-medqa.dev.v1 \
  --registry_path ./registry \
  --max_samples 1 \
  --extra_eval_params temperature=0.1,max_tokens=2048 \
  --local-run \
  --record_path ./experiments/runs/medical-medqa-smoke.jsonl \
  --log_to_file ./experiments/runs/medical-medqa-smoke.log
```

运行完整开发集时去掉 `--max_samples 1`：

```bash
uv run oaieval medical-openai-compatible medical-medqa.dev.v1 \
  --registry_path ./registry \
  --local-run \
  --record_path ./experiments/runs/medical-medqa-dev.jsonl \
  --log_to_file ./experiments/runs/medical-medqa-dev.log
```

## 6. 结果检查

最终报告包含 `accuracy`、`parse_success_rate`、`sample_count`、
`completed_count`、`failed_count`、模型名称和运行时长。分析结果时建议同时检查：

1. `parse_success_rate` 是否明显低于 1；
2. `failed_count` 是否大于 0；
3. sampling 事件中的实际模型名称是否符合预期；
4. 运行记录中的 prompt 是否没有泄漏标准答案；
5. 生成参数是否与实验记录一致。

准确率只反映最终选项是否正确，不等价于临床安全性，也不能替代人工医学审查。

## 7. 测试与扩展

相关测试：

```bash
uv run pytest -q \
  tests/medical_evals/test_medqa_dataset.py \
  tests/medical_evals/test_medqa_eval.py \
  tests/medical_evals/test_choice_parser.py \
  tests/integration/test_medqa_pipeline.py
```

新增 MedQA 数据版本时，应新增明确的 Registry ID 或数据路径，并保持数据契约不变。
如果需要支持五选项、多个正确答案或解释质量评分，应新增独立 Eval/数据契约，
不要隐式改变 `medical-medqa.dev.v1` 的含义。
