# Unified Evaluation Core Design

## Status

Approved in conversation on 2026-08-20. This specification defines the shared evaluation semantics used by both the external `oaieval` CLI and the Workbench worker.

## Context

The repository currently has two evaluation paths:

- The external CLI loads `medical_evals.evals.MedQAEval` or `HealthBenchEval` through the Evals Registry and calls models through `OpenAICompatibleCompletionFn`.
- The Workbench worker claims tasks from SQLite and runs `backend/medical_evals_api/evaluator_adapter.py` through a separate HTTP client.

Both paths reuse dataset loaders, the MedQA choice parser, and some rubric utilities, but they duplicate prompts, request behavior, retry handling, sample evaluation, error classification, and result aggregation. As a result, the same benchmark can behave differently depending on its entry point.

## Goals

1. Make MedQA and HealthBench evaluation semantics identical across CLI and Workbench.
2. Preserve the existing `uv run oaieval ...` command, Registry definitions, Recorder sample IDs, and JSONL event fields.
3. Preserve the Workbench API, database schema, task lifecycle, checkpoint behavior, cancellation, logs, and frontend contract.
4. Provide a stateless, thread-safe core that can support Workbench concurrency in a later change.
5. Move the current automatic retry behavior into the shared model-call path without losing retry observability.

## Non-goals

- Adding Workbench sample concurrency or changing worker task concurrency.
- Replacing the external Evals framework or its CLI.
- Making the CLI depend on FastAPI, SQLite, encrypted Workbench credentials, or backend task models.
- Making the shared core write Recorder events, database rows, artifacts, or logs directly.
- Changing datasets, prompts, scoring formulas, frontend routes, or database schemas except where this specification explicitly resolves an existing cross-entry-point inconsistency.

## Chosen Architecture

Create an entry-point-independent evaluation package under `medical_evals/core/`. The package owns model request semantics, retry behavior, prompts, parsing, rubric judgment, normalized sample results, error categories, and metric aggregation.

The two entry points remain thin orchestration adapters:

- CLI classes retain Evals lifecycle and scheduling, establish Recorder sample contexts, call the shared core for each sample, and translate normalized results into existing sampling, match, error, and final-report fields.
- The Workbench adapter retains task loading, cancellation checks, checkpoints, progress updates, artifact persistence, and database writes. It calls the same core and translates normalized results into the existing Workbench dictionaries and `EvaluationRunResult`.

The shared core never imports `evals`, `medical_evals_api`, FastAPI, SQLite, or Workbench schemas.

```text
                         medical_evals/core
                  prompts · requests · retry · scoring
                           /                 \
              CLI/Evals adapter       Workbench adapter
              Recorder + JSONL        queue + DB + artifacts
```

## Package Responsibilities

### `medical_evals/core/protocols.py`

Defines entry-point-neutral contracts:

- `ModelClient.complete(request, on_event=None) -> ModelResponse`
- `EvaluationEvent` for request-started, request-completed, retry, parse, score, and failure notifications.
- A cancellation callback type used only by shared serial helpers when needed.

The protocol accepts strings or OpenAI-style chat message lists. It does not expose provider SDK response classes.

### `medical_evals/core/models.py`

Defines immutable normalized values:

- `CompletionRequest`: prompt/messages, model, temperature, and max tokens.
- `ModelResponse`: text, actual model name when available, token usage, latency, and retry count.
- `SampleError`: category, message, stage, and retry count.
- `MedQASampleResult` and `HealthBenchSampleResult`.
- `EvaluationSummary`: total, request-success, sample-failure, parse-failure, retry, score, and dimension metrics.

Adapters serialize these values into their existing public dictionaries and Recorder events.

### `medical_evals/core/openai_compatible.py`

Implements the shared OpenAI-compatible request behavior. Both entry points construct or wrap this implementation rather than maintaining independent retry loops.

It normalizes provider exceptions, emits retry events, captures usage and latency where available, and returns `ModelResponse`. Credentials remain constructor inputs and are never included in events or results.

### `medical_evals/core/retry.py`

Defines retry classification and exponential backoff. Transport adapters normalize SDK- or HTTP-specific exceptions into the common policy.

### `medical_evals/core/medqa.py`

Owns the existing Chinese prompt, one-sample model request, choice parsing, normalized sample result, and aggregate metrics.

### `medical_evals/core/healthbench.py`

Owns target prompt construction, target request, per-rubric judge request and parsing, rubric scoring, tag aggregation, normalized sample result, and aggregate metrics.

## Scheduling and Thread Safety

Scheduling remains an entry-point responsibility in this migration:

- CLI continues to use Evals `eval_all_samples`, including its existing `EVALS_THREADS` and `EVALS_SEQUENTIAL` behavior.
- Workbench continues to evaluate samples serially so cancellation, checkpoint ordering, artifact appends, and SQLite updates retain their current behavior.

Core evaluators are stateless. Per-call request and retry state is returned in result objects rather than stored in shared mutable fields such as `last_retry_count`. This makes concurrent CLI calls safe and prepares the Workbench for a separate bounded-concurrency change.

## Data Flow

### CLI

1. Evals loads the existing Registry class and CompletionFn name.
2. `eval_all_samples` establishes the existing Recorder sample ID and invokes `eval_sample`.
3. The CLI adapter converts its CompletionFn/model configuration into the core `ModelClient` contract.
4. The core evaluates one sample and returns a normalized result.
5. The CLI adapter records the existing sampling and match fields.
6. Shared aggregation produces the benchmark metrics; the CLI adds timing, status, and model metadata to its existing final report.

### Workbench

1. The worker claims a queued task and prepares callbacks, artifacts, and checkpoint state.
2. The Workbench adapter loads the dataset and skips successful checkpoint records.
3. It creates the shared model client with decrypted credentials at the boundary.
4. The core evaluates one sample and returns a normalized result.
5. The adapter serializes the result, persists it, and updates task progress.
6. Shared aggregation produces metrics; the worker stores them using the existing result schema.

## Error and Retry Semantics

The shared policy allows two retries after the initial request. Delays are one second and two seconds.

Retryable failures are:

- Network and connection errors.
- Timeouts.
- HTTP 408, 409, 429, 500, 502, 503, and 504.
- An otherwise successful response with no usable message content.

Authentication failures, missing models/endpoints, and other deterministic client errors are not retried.

MedQA choice parse failure does not trigger another model request. It is a successful request with `parse_failed=true`, receives an incorrect score, and is counted separately from request failure.

For HealthBench, invalid judge JSON receives one additional judge request. If the second judgment is invalid, or a target/judge request exhausts transport retries, the sample fails and is excluded from rubric-score aggregation. The system does not rerun an already successful complete target-plus-judge flow.

Retry counts are summed across all requests belonging to a sample and then across the run. Events and persisted errors include only sanitized category, stage, attempt, and message data. API keys and authorization headers are never recorded.

## Metric Semantics

### MedQA

- Accuracy uses all selected samples as its denominator; request failures and parse failures are incorrect answers.
- Parse success rate uses request-successful samples as its denominator.
- Request success, parse failure, sample failure, and retry counts are reported separately.

### HealthBench

- Overall and tag scores aggregate only successfully judged samples.
- Failed samples are reported separately and do not become negative rubric judgments.
- A valid rubric judgment with `criteria_met=false` remains a genuine negative score.

These definitions are applied by the shared aggregators and translated without recomputation by both entry points.

## Compatibility Requirements

### CLI

- `uv run oaieval <completion-fn> <eval> ...` remains valid.
- Existing Registry names and YAML files remain valid.
- Recorder sampling and match fields used by current tests remain present, including prompt, completion, model, usage, latency, expected, picked, sampled, rubric results, scores, and tags.
- Existing sample IDs remain controlled by Evals.
- CLI scheduling environment variables retain their current behavior.

### Workbench

- No API route, request/response schema, database migration, or frontend change is required.
- Existing task statuses, progress fields, result fields, artifact files, cancellation, and checkpoint resume continue to work.
- Existing successful checkpoint records remain readable.
- Current request-level automatic retry behavior remains visible in logs and `retry_count`.

## Migration Sequence

1. Add cross-entry-point contract tests and the core model/result contracts.
2. Introduce the shared OpenAI-compatible client and retry policy, then adapt CLI and Workbench callers while preserving public event/result shapes.
3. Move MedQA prompt, sample execution, parsing, and aggregation into the core; migrate both adapters and remove duplicate MedQA logic.
4. Move HealthBench target/judge execution, judgment parsing, scoring, and aggregation into the core; migrate both adapters and remove duplicate HealthBench logic.
5. Run all unit, integration, backend, and CLI compatibility tests and update architecture documentation.

Each migration stage must leave both entry points runnable and testable.

## Testing Strategy

### Core unit tests

- Prompt construction and request parameters.
- Retryable and non-retryable error classification.
- Backoff sequence, retry counts, empty-response handling, and sanitized events.
- MedQA correct, incorrect, parse-failed, and request-failed results.
- HealthBench positive/negative rubrics, tag aggregation, invalid judge JSON, and request failure.
- Aggregate denominator rules.

### Cross-entry-point contract tests

Feed the same deterministic target and judge outputs through CLI and Workbench adapters and compare normalized fields and aggregate metrics. Cover one successful case and each distinct failure category.

### Compatibility tests

- Existing `oaieval` parser, Registry loading, Recorder, and JSONL event tests continue to pass.
- Existing worker persistence, checkpoint, cancellation, task status, progress, and API result tests continue to pass.
- Existing retry tests are moved or extended so both entry points prove the shared policy.

### Full verification

Run the complete root and backend Python test suites. Frontend tests are required only if an unexpected API contract change is discovered; the design intends no frontend changes.

## Completion Criteria

The migration is complete when:

1. CLI and Workbench use the same core MedQA and HealthBench sample evaluators and aggregators.
2. Identical samples and deterministic model outputs produce identical normalized results, retry counts, error categories, and metrics.
3. Existing CLI commands, Registry entries, Recorder fields, and Workbench API/database contracts pass their compatibility tests.
4. Duplicate prompt, parsing, scoring, retry-policy, and error-classification implementations are removed from entry-point adapters.
5. Workbench remains serial, while core sample evaluation is safe for the CLI's existing threaded execution.

