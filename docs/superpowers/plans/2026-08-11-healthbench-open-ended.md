# HealthBench Open-Ended Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Registry-runnable HealthBench open-ended medical QA evaluation that generates model answers, judges each rubric criterion, and reports weighted overall and tag-level scores.

**Architecture:** Keep the existing single target `CompletionFn` boundary for the evaluated model. `HealthBenchEval` creates a second judge CompletionFn from an injected test object or the existing Registry using `judge_completion_fn`; the judge receives prompt, answer, and one criterion, while the target model never receives rubrics. Dataset loading, rubric scoring, judge parsing, and Eval orchestration remain separate modules.

**Tech Stack:** Python 3.12, existing `evals.Eval`, `CompletionFn`, Recorder, YAML Registry, pytest, JSONL.

## Global Constraints

- Do not add a provider SDK or third-party dependency.
- Do not expose HealthBench rubrics to the evaluated model.
- Keep the existing MedQA behavior and Registry entries unchanged.
- Judge output must be parsed as structured JSON with a boolean `criteria_met` and string `explanation`.
- A failed individual judge call is recorded as an unmet criterion and does not abort later samples.
- HealthBench full data remains under `dataset/HealthBench`; Registry smoke data is copied into `registry/data/medical_healthbench`.

## File Map

- Create `medical-evals/medical_evals/datasets/healthbench.py`: HealthBench JSONL validation and normalization.
- Modify `medical-evals/medical_evals/datasets/__init__.py`: export HealthBench loader.
- Create `medical-evals/medical_evals/metrics/healthbench.py`: rubric, sample, overall, and tag scoring.
- Modify `medical-evals/medical_evals/metrics/__init__.py`: export public scoring helpers.
- Create `medical-evals/medical_evals/judges/rubric.py`: judge prompt, result parser, and Registry/injected CompletionFn adapter.
- Modify `medical-evals/medical_evals/judges/__init__.py`: export judge helpers.
- Create `medical-evals/medical_evals/evals/healthbench.py`: HealthBench Eval orchestration and reports.
- Modify `medical-evals/medical_evals/evals/__init__.py`: export `HealthBenchEval`.
- Create `medical-evals/registry/data/medical_healthbench/smoke.jsonl`: two minimal open-ended samples.
- Create `medical-evals/registry/evals/medical_healthbench.yaml`: base eval plus main, hard, consensus, and smoke IDs.
- Create `medical-evals/tests/medical_evals/test_healthbench_dataset.py`.
- Create `medical-evals/tests/metrics/test_healthbench.py`.
- Create `medical-evals/tests/medical_evals/test_healthbench_judge.py`.
- Create `medical-evals/tests/medical_evals/test_healthbench_eval.py`.
- Create `medical-evals/tests/integration/test_healthbench_pipeline.py`.

### Task 1: Add the validated HealthBench dataset loader

**Files:**
- Create: `medical-evals/medical_evals/datasets/healthbench.py`
- Modify: `medical-evals/medical_evals/datasets/__init__.py`
- Test: `medical-evals/tests/medical_evals/test_healthbench_dataset.py`

**Interfaces:**
- Produce `load_healthbench_samples(path: str | Path) -> list[dict]`.
- Preserve all original top-level fields and normalize missing rubric `tags` to `[]`.
- Reject malformed rows with `ValueError` messages containing the JSONL line number.

- [ ] **Step 1: Write failing loader tests**

```python
def test_load_healthbench_samples_normalizes_tags_and_preserves_fields(tmp_path):
    path = tmp_path / "healthbench.jsonl"
    path.write_text(json.dumps({
        "prompt_id": "p1",
        "prompt": [{"role": "user", "content": "What should I do?"}],
        "rubrics": [{"criterion": "Gives safe advice", "points": 10}],
        "ideal_completions_data": None,
    }) + "\n", encoding="utf-8")
    samples = load_healthbench_samples(path)
    assert samples[0]["prompt_id"] == "p1"
    assert samples[0]["rubrics"][0]["tags"] == []
    assert samples[0]["ideal_completions_data"] is None


@pytest.mark.parametrize("payload", [
    {"prompt_id": "p1", "prompt": [], "rubrics": []},
    {"prompt_id": "p1", "prompt": [{"role": "user"}], "rubrics": [{"criterion": "x", "points": 1}]},
    {"prompt_id": "p1", "prompt": [{"role": "user", "content": "x"}], "rubrics": [{"criterion": "x", "points": "1"}]},
])
def test_loader_rejects_invalid_rows(tmp_path, payload):
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_healthbench_samples(path)
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `cd medical-evals && uv run pytest -q tests/medical_evals/test_healthbench_dataset.py`

Expected: import failure because the loader module does not exist.

- [ ] **Step 3: Implement validation and normalization**

Implement `_validate_sample` and `load_healthbench_samples` using `json.loads`, UTF-8 `Path.open`, blank-line skipping, and explicit checks for `prompt_id`, `prompt`, message `role`/`content`, `rubrics`, rubric `criterion`/`points`, and optional list `tags`.

- [ ] **Step 4: Export the loader and rerun tests**

Run: `cd medical-evals && uv run pytest -q tests/medical_evals/test_healthbench_dataset.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add medical_evals/datasets/healthbench.py medical_evals/datasets/__init__.py tests/medical_evals/test_healthbench_dataset.py
git commit -m "feat: add HealthBench dataset loader"
```

### Task 2: Implement pure HealthBench rubric metrics

**Files:**
- Create: `medical-evals/medical_evals/metrics/healthbench.py`
- Modify: `medical-evals/medical_evals/metrics/__init__.py`
- Test: `medical-evals/tests/metrics/test_healthbench.py`

**Interfaces:**
- `score_rubrics(rubrics: Sequence[dict], results: Sequence[dict]) -> dict` returns `achieved`, `positive_max`, and `score`.
- `score_sample(rubrics: Sequence[dict], results: Sequence[dict]) -> dict` is an alias-level sample helper with the same result shape.
- `aggregate_samples(sample_scores: Sequence[dict]) -> float` returns a clipped mean.
- `aggregate_tag_scores(rubrics: Sequence[dict], results: Sequence[dict]) -> dict[str, float]` returns clipped tag scores.

- [ ] **Step 1: Write failing metric tests**

```python
def test_score_rubrics_applies_positive_max_and_negative_penalty():
    rubrics = [
        {"criterion": "safe", "points": 10, "tags": ["safety"]},
        {"criterion": "complete", "points": 6, "tags": ["completeness"]},
        {"criterion": "harmful", "points": -5, "tags": ["safety"]},
    ]
    results = [
        {"criteria_met": True}, {"criteria_met": False}, {"criteria_met": True}
    ]
    assert score_rubrics(rubrics, results) == {
        "achieved": 5.0, "positive_max": 16.0, "score": 5 / 16,
    }


def test_metric_handles_no_positive_points_and_clips_aggregate():
    assert score_rubrics([{"criterion": "x", "points": -3, "tags": ["x"]}], [{"criteria_met": True}])["score"] == 0.0
    assert aggregate_samples([{"score": -1.0}, {"score": 2.0}]) == 0.5
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `cd medical-evals && uv run pytest -q tests/metrics/test_healthbench.py`

Expected: import or symbol failure.

- [ ] **Step 3: Implement the pure scoring functions**

Join rubric and result by position, treat only literal `True` as met, include negative points only in `achieved`, use `0.0` for a zero denominator, and clip aggregate values with `min(1.0, max(0.0, value))`.

- [ ] **Step 4: Export and verify**

Run: `cd medical-evals && uv run pytest -q tests/metrics/test_healthbench.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add medical_evals/metrics/healthbench.py medical_evals/metrics/__init__.py tests/metrics/test_healthbench.py
git commit -m "feat: add HealthBench weighted rubric metrics"
```

### Task 3: Add the rubric judge adapter and parser

**Files:**
- Create: `medical-evals/medical_evals/judges/rubric.py`
- Modify: `medical-evals/medical_evals/judges/__init__.py`
- Test: `medical-evals/tests/medical_evals/test_healthbench_judge.py`

**Interfaces:**
- `build_rubric_judge_prompt(prompt: list[dict], answer: str, criterion: str) -> list[dict]` returns chat messages for the judge.
- `parse_rubric_judgment(text: str) -> dict` returns `criteria_met: bool` and `explanation: str`.
- `RubricJudge(completion_fn)` exposes `judge(prompt, answer, criterion) -> dict` and calls the supplied CompletionFn with `temperature=0.0`, `max_tokens=256`.
- `resolve_judge_completion_fn(value, registry)` accepts an injected CompletionFn or a registry completion-fn name string.

- [ ] **Step 1: Write failing parser and prompt tests**

```python
def test_parser_accepts_json_and_markdown_fence():
    assert parse_rubric_judgment('{"criteria_met": true, "explanation": "yes"}') == {
        "criteria_met": True, "explanation": "yes",
    }
    assert parse_rubric_judgment('```json\n{"criteria_met": false, "explanation": "no"}\n```')["criteria_met"] is False


def test_judge_prompt_contains_context_but_not_hidden_reference_fields():
    prompt = build_rubric_judge_prompt(
        [{"role": "user", "content": "I have a fever."}], "Seek care if severe.", "Mentions red flags"
    )
    serialized = json.dumps(prompt, ensure_ascii=False)
    assert "I have a fever." in serialized
    assert "Seek care if severe." in serialized
    assert "Mentions red flags" in serialized
    assert "ideal_completions_data" not in serialized
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd medical-evals && uv run pytest -q tests/medical_evals/test_healthbench_judge.py`

Expected: import failure.

- [ ] **Step 3: Implement strict parser and adapter**

Strip optional Markdown code fences, parse one JSON object, require `criteria_met` to be `bool`, coerce only a missing/`None` explanation to an empty string, and raise `ValueError` for all other malformed output. `RubricJudge.judge` should extract the first completion and parse it; caller-owned error handling will isolate failures.

- [ ] **Step 4: Add call-argument and Registry-resolution tests**

Use a fake CompletionFn that records prompts and kwargs; assert one call, `temperature=0.0`, `max_tokens=256`, and that a string value is resolved by `Registry.make_completion_fn` while an object is returned unchanged.

- [ ] **Step 5: Run tests and commit**

Run: `cd medical-evals && uv run pytest -q tests/medical_evals/test_healthbench_judge.py`

```bash
git add medical_evals/judges/rubric.py medical_evals/judges/__init__.py tests/medical_evals/test_healthbench_judge.py
git commit -m "feat: add HealthBench rubric judge"
```

### Task 4: Implement HealthBenchEval orchestration

**Files:**
- Create: `medical-evals/medical_evals/evals/healthbench.py`
- Modify: `medical-evals/medical_evals/evals/__init__.py`
- Test: `medical-evals/tests/medical_evals/test_healthbench_eval.py`

**Interfaces:**
- `HealthBenchEval(..., judge_completion_fn=None, judge_model=None, judge_temperature=0.0, judge_max_tokens=256, **kwargs)` extends `evals.Eval`.
- `build_model_prompt(sample) -> list[dict]` returns only the sample prompt messages.
- `eval_sample` records one model answer and one `match` event per sample, with `rubric_results` and weighted scores.
- `run` returns `overall_score`, `tag_scores`, status, counts, model, judge_model, and timing.

- [ ] **Step 1: Write failing Eval tests**

Create a two-sample JSONL fixture and fake target/judge CompletionFns. Assert the target prompts contain the user messages and never contain rubric criterion text; assert the judge sees the target answer and criterion; assert each match event includes `prompt_id`, `rubric_results`, `achieved`, `positive_max`, and `score`.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd medical-evals && uv run pytest -q tests/medical_evals/test_healthbench_eval.py`

Expected: import failure.

- [ ] **Step 3: Implement constructor and judge resolution**

Call `super().__init__`, resolve an injected object directly or call `self.registry.make_completion_fn(judge_completion_fn)` for a string, defaulting to the target CompletionFn only when no judge is supplied. Store judge generation parameters and expose `_model_name`/`_judge_model_name` using adapter `.model` fallback.

- [ ] **Step 4: Implement sample evaluation and failure isolation**

Call target CompletionFn with `temperature` and `max_tokens` constructor parameters, then judge each rubric independently. On a judge exception, append `{criteria_met: False, explanation: "judge_error: ...", error: ...}` and continue. Record `match` with `correct=score >= 0.5`, `expected=None`, `picked=score`, plus the detailed fields. Do not call `record_sampling` manually because the adapter owns sampling events.

- [ ] **Step 5: Implement run report and verify tests**

Load via `load_healthbench_samples`, call `eval_all_samples`, aggregate scores from match events, and record a failed final report before re-raising only for target/data failures. Run the focused suite and expect PASS.

- [ ] **Step 6: Commit**

```bash
git add medical_evals/evals/healthbench.py medical_evals/evals/__init__.py tests/medical_evals/test_healthbench_eval.py
git commit -m "feat: add HealthBench evaluation orchestration"
```

### Task 5: Register smoke, main, hard, and consensus evaluations

**Files:**
- Create: `medical-evals/registry/data/medical_healthbench/smoke.jsonl`
- Create: `medical-evals/registry/evals/medical_healthbench.yaml`
- Create: `medical-evals/tests/integration/test_healthbench_pipeline.py`

**Interfaces:**
- Base ID: `medical-healthbench` with metrics `overall_score`.
- Smoke ID: `medical-healthbench.smoke.v1` uses `medical_healthbench/smoke.jsonl`.
- Main ID: `medical-healthbench.oss.v1` references `../../../../dataset/HealthBench/2025-05-07-06-14-12_oss_eval.jsonl`.
- Hard ID: `medical-healthbench.hard.v1` references `../../../../dataset/HealthBench/hard_2025-05-08-21-00-10.jsonl`.
- Consensus ID: `medical-healthbench.consensus.v1` references `../../../../dataset/HealthBench/consensus_2025-05-09-20-00-46.jsonl`.

- [ ] **Step 1: Add two smoke samples**

Create valid samples with one user message and two rubrics each, including a positive and a negative criterion, so the integration test exercises weighted scoring without copying the full dataset.

- [ ] **Step 2: Add Registry definitions**

Set `judge_completion_fn: medical-openai-compatible`, `temperature: 0.1`, `max_tokens: 1024`, `judge_temperature: 0.0`, and `judge_max_tokens: 256`. Keep full-data paths as explicit relative paths from the Registry `data` directory; four `..` components are required to reach the repository root from `registry/data`.

- [ ] **Step 3: Write failing Registry and fake-client integration tests**

Use a fake chat client returning a target answer on the first call and a judge JSON object on subsequent calls. Assert Registry resolves all four IDs, target and judge calls are made, the target request does not contain rubric text, one sample produces one sampling event and one match event, and the result includes `overall_score` and `tag_scores`.

- [ ] **Step 4: Run the integration tests and fix only in-scope issues**

Run: `cd medical-evals && uv run pytest -q tests/integration/test_healthbench_pipeline.py`

Expected: PASS after wiring Registry and adapter behavior.

- [ ] **Step 5: Commit**

```bash
git add registry/data/medical_healthbench/smoke.jsonl registry/evals/medical_healthbench.yaml tests/integration/test_healthbench_pipeline.py
git commit -m "feat: register HealthBench evaluation sets"
```

### Task 6: Run the complete verification suite and document usage

**Files:**
- Modify: `medical-evals/README.md`
- Modify: `medical-evals/docs/run-evals.md`

- [ ] **Step 1: Add a concise run example**

Document the smoke command:

```bash
cd medical-evals
OPENAI_API_KEY=xxx OPENAI_BASE_URL=https://example.com/v1 OPENAI_MODEL=your-model \
uv run oaieval medical-openai-compatible medical-healthbench.smoke.v1 \
  --max_samples 2 --local-run
```

Explain that `judge_completion_fn` defaults to the registered compatible adapter and that full datasets are referenced from `dataset/HealthBench`.

- [ ] **Step 2: Run focused and full tests**

Run:

```bash
cd medical-evals
uv run pytest -q tests/medical_evals/test_healthbench_dataset.py tests/metrics/test_healthbench.py tests/medical_evals/test_healthbench_judge.py tests/medical_evals/test_healthbench_eval.py tests/integration/test_healthbench_pipeline.py
uv run pytest -q
```

Expected: both commands pass without changing existing MedQA tests.

- [ ] **Step 3: Inspect the final diff and commit documentation**

```bash
git diff --check
git status --short
git add README.md docs/run-evals.md
git commit -m "docs: document HealthBench evaluation usage"
```
