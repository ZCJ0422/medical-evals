# Unified Evaluation Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the external `oaieval` CLI and the Workbench worker use one shared MedQA/HealthBench evaluation core while preserving their public commands, records, APIs, and orchestration responsibilities.

**Architecture:** Add a dependency-neutral `medical_evals.core` package containing model contracts, retry/error semantics, normalized sample results, sample evaluators, and aggregators. The Evals classes and Workbench adapter become thin translators around this core; Evals retains Recorder/thread scheduling, while Workbench retains queueing, cancellation, checkpoints, artifacts, and serial progress updates.

**Tech Stack:** Python 3.12, dataclasses, typing Protocol, OpenAI Python SDK, OpenAI Evals, FastAPI/Pydantic backend, pytest.

**Spec:** `docs/superpowers/specs/2026-08-20-unified-evaluation-core-design.md`

## Global Constraints

- Preserve `uv run oaieval ...`, Registry names, Recorder sample IDs, and existing sampling/match JSONL fields.
- Preserve Workbench routes, schemas, SQLite schema, task states, cancellation, checkpoints, and frontend contract.
- Workbench sample execution remains serial; CLI retains existing `EVALS_THREADS` and `EVALS_SEQUENTIAL` behavior.
- Core modules must not import `evals`, `medical_evals_api`, FastAPI, SQLite, or Workbench schemas.
- Core evaluators must be stateless; retry counts belong to each returned response/result, not shared mutable client state.
- Default request policy is one initial attempt plus two retries with one-second and two-second backoff.
- Do not stage or alter `docs/项目进展评估-2026-08-20.md`.
- Preserve the intent of the current uncommitted retry changes while replacing their duplicated implementation with the shared core.

---

### Task 1: Add core contracts, normalized results, and retry classification

**Files:**
- Create: `medical_evals/core/__init__.py`
- Create: `medical_evals/core/models.py`
- Create: `medical_evals/core/protocols.py`
- Create: `medical_evals/core/retry.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_models.py`
- Create: `tests/core/test_retry.py`

**Interfaces:**
- Produces: `CompletionRequest`, `ModelResponse`, `SampleError`, `MedQASampleResult`, `HealthBenchSampleResult`, `EvaluationSummary`, `EvaluationEvent`, `ModelClient`, `classify_error()`, `is_retryable_error()`, and `retry_delay_seconds()`.
- Consumes: Python standard library only.

- [ ] **Step 1: Write failing contract tests**

```python
# tests/core/test_models.py
from medical_evals.core.models import CompletionRequest, ModelResponse


def test_model_response_keeps_retry_state_per_response():
    request = CompletionRequest(
        prompt="question",
        model="model-a",
        temperature=0.1,
        max_tokens=5120,
    )
    first = ModelResponse(text="A", model="model-a", retry_count=1)
    second = ModelResponse(text="B", model="model-a", retry_count=0)

    assert request.model == "model-a"
    assert first.retry_count == 1
    assert second.retry_count == 0
```

```python
# tests/core/test_retry.py
from medical_evals.core.retry import classify_status_code, retry_delay_seconds


def test_retryable_status_codes_and_backoff_are_canonical():
    assert classify_status_code(429) == ("rate_limit_error", True)
    assert classify_status_code(503) == ("request_error", True)
    assert classify_status_code(401) == ("authentication_error", False)
    assert classify_status_code(404) == ("model_or_endpoint_error", False)
    assert retry_delay_seconds(1) == 1.0
    assert retry_delay_seconds(2) == 2.0
```

- [ ] **Step 2: Run tests and verify the missing-package failure**

Run:

```bash
.venv/bin/pytest tests/core/test_models.py tests/core/test_retry.py -q
```

Expected: collection fails because `medical_evals.core` does not exist.

- [ ] **Step 3: Implement immutable contracts and retry helpers**

Use these public shapes:

```python
# medical_evals/core/protocols.py
from collections.abc import Callable
from typing import Protocol

from .models import CompletionRequest, EvaluationEvent, ModelResponse

EventCallback = Callable[[EvaluationEvent], None]


class ModelClient(Protocol):
    def complete(
        self,
        request: CompletionRequest,
        on_event: EventCallback | None = None,
    ) -> ModelResponse: ...
```

```python
# medical_evals/core/models.py
from dataclasses import dataclass, field
from typing import Any

Prompt = str | list[dict[str, Any]]


@dataclass(frozen=True)
class CompletionRequest:
    prompt: Prompt
    model: str
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class EvaluationEvent:
    kind: str
    stage: str
    attempt: int = 1
    category: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model: str | None = None
    usage: dict[str, Any] | None = None
    usage_details: dict[str, Any] | None = None
    latency: float = 0.0
    retry_count: int = 0
    raw_response: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class SampleError:
    category: str
    message: str
    stage: str
    retry_count: int = 0


@dataclass(frozen=True)
class MedQASampleResult:
    sample_id: str
    expected: str
    predicted: str | None
    raw_output: str
    correct: bool
    parse_failed: bool
    retry_count: int
    error: SampleError | None = None


@dataclass(frozen=True)
class HealthBenchSampleResult:
    sample_id: str
    raw_output: str
    rubric_judgments: tuple[dict[str, Any], ...]
    score: float | None
    achieved: float | None
    positive_max: float | None
    tag_scores: dict[str, float]
    retry_count: int
    error: SampleError | None = None


@dataclass(frozen=True)
class EvaluationSummary:
    total_count: int
    success_count: int
    failed_count: int
    retry_count: int
    total_score: float
    dimensions: dict[str, float]
    request_success_count: int
    parse_failed_count: int = 0
    parse_success_rate: float | None = None
    error_categories: dict[str, int] = field(default_factory=dict)
```

Implement `classify_status_code()` with the exact status categories asserted above, `retry_delay_seconds(retry_number)` as `2 ** (retry_number - 1)`, and provider-neutral helpers that recognize normalized timeout/network flags without importing provider SDKs.

- [ ] **Step 4: Run the new unit tests**

Run:

```bash
.venv/bin/pytest tests/core/test_models.py tests/core/test_retry.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit the contracts**

```bash
git add medical_evals/core tests/core
git commit -m "feat: add evaluation core contracts"
```

---

### Task 2: Replace duplicate OpenAI-compatible retry clients with one core client

**Files:**
- Create: `medical_evals/core/openai_compatible.py`
- Create: `tests/core/test_openai_compatible.py`
- Modify: `medical_evals/adapters/openai_compatible.py`
- Modify: `tests/adapters/test_openai_compatible.py`
- Modify: `backend/medical_evals_api/openai_compatible.py`
- Modify: `backend/tests/test_openai_compatible.py`

**Interfaces:**
- Consumes: `CompletionRequest`, `EvaluationEvent`, `ModelResponse`, retry helpers from Task 1.
- Produces: `OpenAICompatibleClient.complete(request, on_event=None)`, `EmptyCompletionError`, `OpenAICompatibleCompletionFn.complete_core(request, on_event=None)`, the existing CLI CompletionFn surface, and a temporary dual-signature backend compatibility wrapper.

- [ ] **Step 1: Write failing shared-client tests**

```python
# tests/core/test_openai_compatible.py
from types import SimpleNamespace

import pytest
from openai import APITimeoutError

from medical_evals.core.models import CompletionRequest
from medical_evals.core.openai_compatible import OpenAICompatibleClient


def request():
    return CompletionRequest("question", "model-a", 0.1, 5120)


def response(text="A"):
    return SimpleNamespace(
        model="model-a",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=1, total_tokens=11),
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


class FakeCompletions:
    def __init__(self, values):
        self.values = iter(values)

    def create(self, **kwargs):
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


class FakeOpenAIClient:
    def __init__(self, values):
        self.chat = SimpleNamespace(completions=FakeCompletions(values))


def test_timeout_retries_are_returned_on_the_response():
    fake_openai_client = FakeOpenAIClient([
        APITimeoutError(request=SimpleNamespace()),
        response("A"),
    ])
    sleeps = []
    events = []
    client = OpenAICompatibleClient(
        model="model-a",
        client=fake_openai_client,
        sleep_fn=sleeps.append,
    )

    result = client.complete(request(), events.append)

    assert result.text == "A"
    assert result.retry_count == 1
    assert sleeps == [1.0]
    assert [event.kind for event in events] == ["request_started", "retry", "request_started", "request_completed"]


def test_retry_count_is_not_shared_between_calls():
    fake_openai_client = FakeOpenAIClient([response("A"), response("B")])
    client = OpenAICompatibleClient(model="model-a", client=fake_openai_client)

    assert client.complete(request()).retry_count == 0
    assert client.complete(request()).retry_count == 0
```

Add tests for 401 without retry, 429 with retry, empty content with two retries, usage serialization, and event messages that do not contain the API key.

- [ ] **Step 2: Run shared-client tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/core/test_openai_compatible.py -q
```

Expected: import fails because the shared client has not been created.

- [ ] **Step 3: Implement the shared client**

Implement this constructor and call surface:

```python
class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        retry_base_seconds: float = 1.0,
        sleep_fn=time.sleep,
        client=None,
    ): ...

    def complete(
        self,
        request: CompletionRequest,
        on_event: EventCallback | None = None,
    ) -> ModelResponse: ...
```

For each call, keep `retry_count` in a local variable, create OpenAI chat arguments from `CompletionRequest`, disable SDK-internal retries, emit sanitized events, and return usage/latency/raw response in `ModelResponse`. Re-raise the original final provider exception so existing exception-type compatibility tests remain valid. Raise `EmptyCompletionError` after the same retry budget when choices/content stay empty.

- [ ] **Step 4: Make the CLI CompletionFn delegate to the shared client**

Keep `OpenAICompatibleCompletionFn` and `OpenAICompatibleCompletionResult` public. Add `error` and `retry_count` to the result wrapper so the Evals adapter can distinguish an exhausted empty response from an ordinary parse failure while direct CompletionFn callers still receive an empty completion.

```python
class OpenAICompatibleCompletionResult(CompletionResult):
    def __init__(self, raw_data, prompt, completions, *, error=None, retry_count=0):
        self.raw_data = raw_data
        self.prompt = prompt
        self.error = error
        self.retry_count = retry_count
        self._completions = list(completions)
```

`OpenAICompatibleCompletionFn.__call__` builds `CompletionRequest`, invokes the shared client, writes existing sampling/error events, and returns the compatibility result. On exhausted `EmptyCompletionError`, record one error and return an empty compatibility result carrying the error. On other final errors, record once and re-raise.

Add `complete_core(request, on_event=None) -> ModelResponse` to `OpenAICompatibleCompletionFn`. It delegates directly to the shared client, forwards core events, records one sampling event on success or one error event on final failure, and re-raises final exceptions. `__call__` remains the compatibility wrapper around `complete_core`; core evaluators reach `complete_core` through the CLI boundary adapter so retry events and per-call counts are preserved.

- [ ] **Step 5: Turn the backend client into a temporary compatibility wrapper**

Keep `medical_evals_api.openai_compatible.OpenAICompatibleClient` importable while MedQA and HealthBench are migrated. Implement it as a subclass of the shared client whose `complete` method accepts either a `CompletionRequest` and returns `ModelResponse`, or the legacy `complete(prompt, *, model, temperature, max_tokens)` call and returns text. The branch must delegate both forms to `super().complete()`; it must not contain its own request or retry loop.

The legacy branch may set `last_retry_count` only to keep the current uncommitted Worker tests passing during this intermediate commit. Task 4 removes the legacy branch and mutable field after Workbench MedQA adopts the core protocol. Do not retain a second retry loop or `_is_retryable_error` implementation in the backend module.

- [ ] **Step 6: Run adapter and backend retry tests**

Run:

```bash
.venv/bin/pytest tests/core/test_openai_compatible.py tests/adapters/test_openai_compatible.py backend/tests/test_openai_compatible.py -q
```

Expected: shared policy and both compatibility surfaces pass.

- [ ] **Step 7: Commit the unified request layer**

```bash
git add medical_evals/core/openai_compatible.py medical_evals/adapters/openai_compatible.py backend/medical_evals_api/openai_compatible.py tests/core/test_openai_compatible.py tests/adapters/test_openai_compatible.py backend/tests/test_openai_compatible.py
git commit -m "refactor: unify openai compatible requests"
```

---

### Task 3: Move MedQA semantics into the shared core and migrate the CLI

**Files:**
- Create: `medical_evals/core/medqa.py`
- Create: `medical_evals/evals/completion_client.py`
- Create: `tests/core/test_medqa.py`
- Modify: `medical_evals/evals/medqa.py`
- Modify: `tests/medical_evals/test_medqa_eval.py`
- Modify: `tests/integration/test_medqa_pipeline.py`

**Interfaces:**
- Consumes: `ModelClient`, core contracts, existing dataset option keys, and `parse_choice`.
- Produces: `build_medqa_prompt()`, `evaluate_medqa_sample()`, `aggregate_medqa()`, and `CompletionFnModelClient` at the CLI boundary.

- [ ] **Step 1: Write failing MedQA core tests**

```python
# tests/core/test_medqa.py
from medical_evals.core.medqa import aggregate_medqa, evaluate_medqa_sample
from medical_evals.core.models import ModelResponse


MEDQA_SAMPLE = {
    "id": "medqa-1",
    "question": "患者出现发热，最常用的体温测量部位是什么？",
    "options": {"A": "皮肤", "B": "眼睛", "C": "口腔", "D": "头发"},
    "answer": "C",
}


class StaticClient:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def complete(self, request, on_event=None):
        self.requests.append(request)
        return self.response


def test_medqa_uses_one_canonical_prompt_and_result_shape():
    client = StaticClient(ModelResponse(text="C", retry_count=1))

    result = evaluate_medqa_sample(client, MEDQA_SAMPLE, model="model-a")

    assert "请只输出一个选项字母" in client.requests[0].prompt
    assert result.predicted == "C"
    assert result.correct is True
    assert result.retry_count == 1


def test_medqa_parse_failure_is_not_a_request_failure():
    client = StaticClient(ModelResponse(text="无法确定"))

    result = evaluate_medqa_sample(client, MEDQA_SAMPLE, model="model-a")

    assert result.parse_failed is True
    assert result.error is None
    assert aggregate_medqa([result]).failed_count == 0
```

Add a request-exception case asserting a normalized `SampleError`, and an aggregate test asserting that request/parse failures are incorrect in the accuracy denominator while parse success uses request-successful samples.

- [ ] **Step 2: Run the core MedQA tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/core/test_medqa.py -q
```

Expected: import fails because `medical_evals.core.medqa` does not exist.

- [ ] **Step 3: Implement canonical MedQA evaluation**

Implement:

```python
def evaluate_medqa_sample(
    client: ModelClient,
    sample: dict,
    *,
    model: str,
    temperature: float = 0.1,
    max_tokens: int = 5120,
    on_event: EventCallback | None = None,
) -> MedQASampleResult: ...


def aggregate_medqa(results: Sequence[MedQASampleResult]) -> EvaluationSummary: ...
```

Use the existing Chinese prompt text unchanged. Catch final model exceptions inside `evaluate_medqa_sample`, normalize them with core retry/error helpers, and return a failed result instead of aborting the whole run.

Wrap the supplied event callback with a per-sample collector. Count `kind="retry"` events locally and use that count in both successful and failed `MedQASampleResult` values; do not read retry state from client attributes.

Create the CLI boundary adapter with this exact contract:

```python
# medical_evals/evals/completion_client.py
class CompletionFnModelClient:
    def __init__(self, completion_fn, *, model: str | None = None):
        self.completion_fn = completion_fn
        self.model = model or getattr(completion_fn, "model", None)

    def complete(self, request: CompletionRequest, on_event=None) -> ModelResponse:
        if hasattr(self.completion_fn, "complete_core"):
            return self.completion_fn.complete_core(request, on_event=on_event)
        result = self.completion_fn(
            prompt=request.prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        if getattr(result, "error", None) is not None:
            raise result.error
        completions = result.get_completions()
        return ModelResponse(
            text=completions[0] if completions else "",
            model=self.model,
            retry_count=int(getattr(result, "retry_count", 0)),
            raw_response=getattr(result, "raw_data", None),
        )
```

- [ ] **Step 4: Migrate `MedQAEval` to the core**

Retain `MedQAEval`, its constructor arguments, `eval_all_samples`, timing fields, and model metadata. Replace its prompt/parse/score logic with `evaluate_medqa_sample`. Translate the result into the same `record_match` keys:

```python
record_match(
    result.correct,
    expected=result.expected,
    picked=result.predicted,
    sampled=result.raw_output,
    options=list(OPTION_KEYS),
    parse_failed=result.parse_failed,
    retry_count=result.retry_count,
    error=result.error.message if result.error else None,
    error_category=result.error.category if result.error else None,
)
```

Use `aggregate_medqa` over returned sample results in `run()` rather than recomputing from Recorder events. Preserve existing final-report names `accuracy`, `parse_success_rate`, `completed_count`, `failed_count`, and `model`.

- [ ] **Step 5: Run MedQA core, eval, and CLI integration tests**

Run:

```bash
.venv/bin/pytest tests/core/test_medqa.py tests/medical_evals/test_medqa_eval.py tests/integration/test_medqa_pipeline.py -q
```

Expected: all MedQA tests pass and existing Recorder fields remain present.

- [ ] **Step 6: Commit the CLI MedQA migration**

```bash
git add medical_evals/core/medqa.py medical_evals/evals/completion_client.py medical_evals/evals/medqa.py tests/core/test_medqa.py tests/medical_evals/test_medqa_eval.py tests/integration/test_medqa_pipeline.py
git commit -m "refactor: move medqa evaluation into core"
```

---

### Task 4: Migrate Workbench MedQA and prove cross-entry-point parity

**Files:**
- Modify: `backend/medical_evals_api/evaluator_adapter.py`
- Modify: `backend/medical_evals_api/openai_compatible.py`
- Modify: `backend/tests/test_real_worker.py`
- Create: `backend/tests/test_medqa_core_parity.py`
- Create: `tests/integration/test_entrypoint_parity.py`

**Interfaces:**
- Consumes: `evaluate_medqa_sample()`, `aggregate_medqa()`, core result types, and backend client compatibility wrapper.
- Produces: unchanged `EvaluationRunResult`, sample artifact dictionaries, progress updates, and retry logs.

- [ ] **Step 1: Write a failing parity test**

```python
# backend/tests/test_medqa_core_parity.py
from medical_evals_api.evaluator_adapter import serialize_medqa_result
from medical_evals.core.medqa import aggregate_medqa, evaluate_medqa_sample
from medical_evals.core.models import ModelResponse


class StaticCoreClient:
    def complete(self, request, on_event=None):
        return ModelResponse(text="C", retry_count=1)


MEDQA_SAMPLE = {
    "id": "medqa-1",
    "question": "question",
    "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
    "answer": "C",
}


def test_workbench_medqa_serialization_matches_core():
    core_result = evaluate_medqa_sample(StaticCoreClient(), MEDQA_SAMPLE, model="model-a")
    adapter_record = serialize_medqa_result(0, MEDQA_SAMPLE, core_result)

    assert adapter_record["predicted"] == core_result.predicted
    assert adapter_record["correct"] == core_result.correct
    assert adapter_record["parse_failed"] == core_result.parse_failed
    assert adapter_record["retry_count"] == core_result.retry_count
```

Expose `serialize_medqa_result(index, sample, result) -> dict` and `deserialize_medqa_record(record) -> MedQASampleResult`. Test success, parse failure, and request failure through those production functions. The deserializer is required so successful checkpoint dictionaries are included in the same shared aggregation path as newly evaluated samples.

- [ ] **Step 2: Run the parity test and verify failure**

Run:

```bash
.venv/bin/pytest backend/tests/test_medqa_core_parity.py -q
```

Expected: import fails because the serializer/core-backed path is absent.

- [ ] **Step 3: Replace Workbench MedQA evaluation with the core**

In `_run_medqa`, retain dataset selection, max-sample handling, cancellation checks, checkpoint reads, `on_sample`, logs, and progress updates. For each non-checkpoint sample:

```python
result = evaluate_medqa_sample(
    target,
    sample,
    model=task.target_model_id,
    temperature=0.1,
    max_tokens=5120,
    on_event=self._core_event,
)
record = serialize_medqa_result(index - 1, sample, result)
```

Translate core events to the existing log prefixes. Use `aggregate_medqa` once after the loop and map its fields to `EvaluationRunResult`. Delete backend-local `_medqa_prompt`, `medqa_metrics`, duplicate exception classification, and the MedQA request retry bookkeeping.

Replace the temporary backend client wrapper with a direct re-export of the shared `OpenAICompatibleClient`, update Workbench construction to keyword arguments, and update injected test clients to implement `complete(CompletionRequest, on_event=None) -> ModelResponse`. At this point, remove `last_retry_count` and the legacy prompt/keyword call branch.

Add the MedQA cases to `tests/integration/test_entrypoint_parity.py`. Run `MedQAEval` with a `DummyRecorder` and the Workbench adapter with the same deterministic model responses, then compare prediction, correctness, parse state, retry count, error category, accuracy, request-success count, parse-failure count, and failed count after removing timestamps and entry-point-specific sample IDs.

- [ ] **Step 4: Run Workbench MedQA tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_medqa_core_parity.py backend/tests/test_real_worker.py backend/tests/test_worker.py tests/integration/test_entrypoint_parity.py -q
```

Expected: all tests pass, including persisted retry count and checkpoint behavior.

- [ ] **Step 5: Commit the Workbench MedQA migration**

```bash
git add backend/medical_evals_api/evaluator_adapter.py backend/medical_evals_api/openai_compatible.py backend/tests/test_real_worker.py backend/tests/test_medqa_core_parity.py tests/integration/test_entrypoint_parity.py
git commit -m "refactor: use evaluation core in workbench medqa"
```

---

### Task 5: Move HealthBench target/judge semantics into the shared core and migrate the CLI

**Files:**
- Create: `medical_evals/core/healthbench.py`
- Create: `tests/core/test_healthbench.py`
- Modify: `medical_evals/evals/healthbench.py`
- Modify: `tests/medical_evals/test_healthbench_eval.py`
- Modify: `tests/integration/test_healthbench_pipeline.py`

**Interfaces:**
- Consumes: two `ModelClient` values, `CompletionFnModelClient`, rubric prompt/parser utilities, `score_rubrics`, and `aggregate_tag_scores`.
- Produces: `evaluate_healthbench_sample()` and `aggregate_healthbench()`.

- [ ] **Step 1: Write failing HealthBench core tests**

```python
# tests/core/test_healthbench.py
from medical_evals.core.healthbench import evaluate_healthbench_sample
from medical_evals.core.models import ModelResponse


HEALTHBENCH_SAMPLE = {
    "prompt_id": "health-1",
    "prompt": [{"role": "user", "content": "What should I do?"}],
    "rubrics": [
        {"criterion": "Mentions urgent care", "points": 1, "tags": ["safety"]},
        {"criterion": "Avoids diagnosis", "points": 1, "tags": ["safety"]},
    ],
}


class QueueClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, request, on_event=None):
        self.requests.append(request)
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def test_healthbench_uses_target_then_judges_each_rubric():
    target = QueueClient([ModelResponse(text="Seek urgent care.")])
    judge = QueueClient([
        ModelResponse(text='{"criteria_met": true, "explanation": "covered"}'),
        ModelResponse(text='{"criteria_met": false, "explanation": "missing"}'),
    ])

    result = evaluate_healthbench_sample(
        target,
        judge,
        HEALTHBENCH_SAMPLE,
        target_model="target-model",
        judge_model="judge-model",
    )

    assert result.error is None
    assert len(result.rubric_judgments) == 2
    assert result.retry_count == 0


def test_invalid_judge_json_gets_one_new_judge_request():
    target = QueueClient([ModelResponse(text="answer")])
    judge = QueueClient([
        ModelResponse(text="invalid"),
        ModelResponse(text='{"criteria_met": true, "explanation": "valid"}'),
    ])

    result = evaluate_healthbench_sample(
        target,
        judge,
        {**HEALTHBENCH_SAMPLE, "rubrics": HEALTHBENCH_SAMPLE["rubrics"][:1]},
        target_model="target-model",
        judge_model="judge-model",
    )

    assert result.error is None
    assert len(judge.requests) == 2
```

Add a second-invalid-JSON case that produces a failed sample, a transport-failure case that does not rerun a successful target request, and aggregation tests proving failed samples are excluded while valid `criteria_met=false` remains a negative score.

- [ ] **Step 2: Run HealthBench core tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/core/test_healthbench.py -q
```

Expected: import fails because the HealthBench core is absent.

- [ ] **Step 3: Implement canonical HealthBench evaluation**

Implement:

```python
def evaluate_healthbench_sample(
    target: ModelClient,
    judge: ModelClient,
    sample: dict,
    *,
    target_model: str,
    judge_model: str,
    target_temperature: float = 0.1,
    target_max_tokens: int = 5120,
    judge_temperature: float = 0.0,
    judge_max_tokens: int = 5120,
    on_event: EventCallback | None = None,
) -> HealthBenchSampleResult: ...


def aggregate_healthbench(
    results: Sequence[HealthBenchSampleResult],
) -> EvaluationSummary: ...
```

Call the target once. For each rubric, call the judge and retry only invalid structured judgment once; transport retries remain inside the shared client. On final failure, return a failed sample with retries accumulated across completed calls. Do not synthesize `criteria_met=false` for infrastructure or parse failures.

- [ ] **Step 4: Migrate `HealthBenchEval` to the core**

Retain Registry judge resolution, CLI constructor parameters, `eval_all_samples`, model metadata, timing fields, and Recorder sample IDs. Translate a successful core result into the existing `record_match` keys. For failed samples, record a false match containing `error` and `error_category`, so the sample remains observable without contaminating rubric aggregation.

Use `aggregate_healthbench` over returned sample results for `overall_score`, `tag_scores`, completed count, and failed count.

- [ ] **Step 5: Run HealthBench core and CLI tests**

Run:

```bash
.venv/bin/pytest tests/core/test_healthbench.py tests/medical_evals/test_healthbench_eval.py tests/integration/test_healthbench_pipeline.py -q
```

Expected: all tests pass and target prompts still exclude rubric criteria.

- [ ] **Step 6: Commit the CLI HealthBench migration**

```bash
git add medical_evals/core/healthbench.py medical_evals/evals/healthbench.py tests/core/test_healthbench.py tests/medical_evals/test_healthbench_eval.py tests/integration/test_healthbench_pipeline.py
git commit -m "refactor: move healthbench evaluation into core"
```

---

### Task 6: Migrate Workbench HealthBench and prove cross-entry-point parity

**Files:**
- Modify: `backend/medical_evals_api/evaluator_adapter.py`
- Modify: `backend/tests/test_healthbench_metrics.py`
- Modify: `backend/tests/test_healthbench_real_worker.py`
- Create: `backend/tests/test_healthbench_core_parity.py`
- Modify: `tests/integration/test_entrypoint_parity.py`

**Interfaces:**
- Consumes: `evaluate_healthbench_sample()`, `aggregate_healthbench()`, and core HealthBench result types.
- Produces: unchanged Workbench records, progress, artifact fields, and `EvaluationRunResult`.

- [ ] **Step 1: Write failing Workbench parity tests**

```python
# backend/tests/test_healthbench_core_parity.py
from medical_evals_api.evaluator_adapter import serialize_healthbench_result
from medical_evals.core.models import HealthBenchSampleResult


def test_workbench_healthbench_serialization_matches_core():
    sample = {"prompt_id": "health-1", "prompt": [], "rubrics": []}
    core_result = HealthBenchSampleResult(
        sample_id="health-1",
        raw_output="answer",
        rubric_judgments=({"criteria_met": True},),
        score=1.0,
        achieved=1.0,
        positive_max=1.0,
        tag_scores={"safety": 1.0},
        retry_count=1,
    )

    record = serialize_healthbench_result(0, sample, core_result)

    assert record["sample_id"] == core_result.sample_id
    assert record["raw_output"] == core_result.raw_output
    assert record["rubric_judgments"] == list(core_result.rubric_judgments)
    assert record["score"] == core_result.score
    assert record["tag_scores"] == core_result.tag_scores
    assert record["retry_count"] == core_result.retry_count
```

Add a failed-result case asserting `error`, `error_category`, and exclusion from aggregate scores.

Expose `deserialize_healthbench_record(record) -> HealthBenchSampleResult` and round-trip both successful and failed records so resumed checkpoints and new results share one aggregation path.

- [ ] **Step 2: Run Workbench HealthBench parity tests and verify failure**

Run:

```bash
.venv/bin/pytest backend/tests/test_healthbench_core_parity.py -q
```

Expected: import fails because the serializer/core-backed path is absent.

- [ ] **Step 3: Replace Workbench HealthBench evaluation with the core**

Retain dataset path resolution, max-sample handling, cancellation, checkpoints, persistence, logs, and progress. Replace `_evaluate_healthbench_sample`, `_judge_healthbench_rubric`, local scoring helpers, and full-flow retry with `evaluate_healthbench_sample`.

Use `aggregate_healthbench` to construct `EvaluationRunResult`. Ensure progress includes aggregate retry count on every update, including HealthBench updates that previously omitted it.

Extend `tests/integration/test_entrypoint_parity.py` with scored, judge-parse-failed, and request-failed HealthBench cases. Compare rubric judgments, score, tag scores, retry count, error category, total score, request-success count, and failed count after removing entry-point metadata.

- [ ] **Step 4: Run Workbench HealthBench tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_healthbench_core_parity.py backend/tests/test_healthbench_metrics.py backend/tests/test_healthbench_real_worker.py tests/integration/test_entrypoint_parity.py -q
```

Expected: all tests pass with failed judge samples excluded from score aggregation.

- [ ] **Step 5: Commit the Workbench HealthBench migration**

```bash
git add backend/medical_evals_api/evaluator_adapter.py backend/tests/test_healthbench_metrics.py backend/tests/test_healthbench_real_worker.py backend/tests/test_healthbench_core_parity.py tests/integration/test_entrypoint_parity.py
git commit -m "refactor: use evaluation core in workbench healthbench"
```

---

### Task 7: Remove dead duplication, run complete compatibility checks, and update documentation

**Files:**
- Modify: `tests/integration/test_entrypoint_parity.py` only if the full run exposes an uncovered compatibility case
- Modify: `medical_evals/core/__init__.py`
- Modify: `backend/medical_evals_api/evaluator_adapter.py`
- Delete: `backend/medical_evals_api/retry.py` if no imports remain
- Modify: `README.md`

**Interfaces:**
- Consumes: all core evaluators, parity tests created in Tasks 4 and 6, and both entry-point translators.
- Produces: one canonical definition for each evaluation behavior plus final regression evidence.

- [ ] **Step 1: Remove remaining duplicate behavior**

Use `rg` to verify prompts, scoring loops, and retry status sets have one canonical definition:

```bash
rg -n "请回答下面的医学单项选择题|RETRYABLE_STATUS_CODES|def .*healthbench.*score|def .*medqa.*metrics" medical_evals backend
```

Keep only core definitions plus imports/translators. Delete `backend/medical_evals_api/retry.py` only after `rg -n "medical_evals_api.retry|from \.retry" backend tests` returns no consumers.

- [ ] **Step 2: Update architecture documentation**

Update README to state that CLI and Workbench share model request, retry, sample evaluation, and aggregation semantics while retaining separate orchestration. Leave the pre-existing untracked project progress report unchanged.

- [ ] **Step 3: Run focused and full verification**

Run:

```bash
.venv/bin/pytest tests/core tests/medical_evals tests/adapters tests/integration backend/tests -q
```

Then run:

```bash
.venv/bin/pytest -q
```

Expected: all project tests pass. Warnings already present in the baseline may remain, but no new failure or error is accepted.

- [ ] **Step 4: Verify repository diff and public imports**

Run:

```bash
git diff --check
git status --short
.venv/bin/python -c "from medical_evals.adapters import OpenAICompatibleCompletionFn; from medical_evals.core.medqa import evaluate_medqa_sample; from medical_evals.core.healthbench import evaluate_healthbench_sample"
```

Expected: no whitespace errors, imports succeed, and the status contains only intended implementation/documentation changes plus the pre-existing untracked progress report if it has not yet been intentionally staged.

- [ ] **Step 5: Commit final parity and documentation changes**

```bash
git add tests/integration/test_entrypoint_parity.py medical_evals/core/__init__.py backend/medical_evals_api/evaluator_adapter.py README.md
git add -u backend/medical_evals_api/retry.py
git commit -m "test: verify cli and workbench evaluation parity"
```

Only include `backend/medical_evals_api/retry.py` in `git add -u` when Task 7 Step 3 proved it has no consumers and deleted it.
