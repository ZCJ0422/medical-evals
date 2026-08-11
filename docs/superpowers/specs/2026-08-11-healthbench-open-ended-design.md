# HealthBench 开放式问答评测设计

## 目标与范围

在 `medical-evals` 中增加开放式医学问答评测链路，优先支持仓库中的 HealthBench 主数据集，并注册 hard、consensus 两个变体。第一版不实现人工标注界面、多轮状态管理或厂商专用 SDK。

数据文件：

- `dataset/HealthBench/2025-05-07-06-14-12_oss_eval.jsonl`
- `dataset/HealthBench/hard_2025-05-08-21-00-10.jsonl`
- `dataset/HealthBench/consensus_2025-05-09-20-00-46.jsonl`

## 数据契约

每行至少包含 `prompt_id`、非空 `prompt` 消息数组和非空 `rubrics` 数组。消息包含 `role` 与字符串 `content`；rubric 包含非空 `criterion`、数值型 `points`，`tags` 缺失时规范化为空列表。`ideal_completions_data` 可以为空并原样保留。非法 JSON、缺字段或错误类型报告行号并抛出 `ValueError`。

## 评测与评分

`HealthBenchEval` 将 prompt 传给被测模型但不暴露 rubric，取得第一个 completion 后，对每条 rubric 调用 `RubricJudge`。Judge 返回：

```json
{"criteria_met": true, "explanation": "..."}
```

单题评分：

```text
achieved = Σ(points_i)，仅累加 criteria_met=true
positive_max = Σ(points_i)，仅累加 points_i > 0
sample_score = achieved / positive_max
```

`positive_max == 0` 时得分为 `0.0`；负分 rubric 参与惩罚但不进入分母；总体均值裁剪到 `[0, 1]`。按 tag 使用对应 rubric 子集计算同样的加权分数。

## 组件边界

- `medical_evals/datasets/healthbench.py`：读取、校验、规范化 JSONL。
- `medical_evals/judges/rubric.py`：Judge 协议、JSON 结果解析与 prompt 构造。
- `medical_evals/metrics/healthbench.py`：单题、总体和 tag 加权聚合。
- `medical_evals/evals/healthbench.py`：编排模型、Judge、Recorder 与 final report。
- `evals/registry/data/medical_healthbench/`：两条 smoke 样本；完整数据仍由配置路径引用仓库根目录文件。

被测模型和 Judge 均通过现有 CompletionFn 接入。Judge 解析失败的 rubric 记为未满足并记录错误，不中断整条评测。

## 输出与测试

逐题记录包含 `prompt_id`、`sampled`、`rubric_results`、`achieved`、`positive_max`、`score`；总体报告包含状态、样本计数、`overall_score`、`tag_scores`、模型信息和耗时。

测试覆盖 loader 校验、正负分与边界、tag 聚合、Judge JSON 解析和参数转发、rubric 不泄露给被测模型、逐题 Recorder 事件、Judge 单条失败隔离，以及三个 Registry ID 和两条样本 smoke 流程。

第一版不使用 BLEU、ROUGE 或 embedding 相似度作为主指标；后续可增加人工复核、多 Judge 投票、bootstrap 区间和主题分析。
