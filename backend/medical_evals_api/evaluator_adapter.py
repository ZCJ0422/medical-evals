from collections.abc import Callable
from dataclasses import dataclass
import os
import time
from typing import cast

from .models import EvaluationTask
from .models.evaluations import EvaluationRun
from .schemas.common import TaskProgress
from .openai_compatible import OpenAICompatibleClient
from .paths import registry_data_path
from .secrets import decrypt_secret
from medical_evals.core.medqa import (
    aggregate_medqa,
    evaluate_medqa_sample,
)
from medical_evals.core.healthbench import (
    aggregate_healthbench,
    evaluate_healthbench_sample,
)
from medical_evals.core.models import CompletionRequest, EvaluationEvent, HealthBenchSampleResult, ModelResponse
from medical_evals.core.protocols import ModelClient
from medical_evals.datasets.medqa import load_medqa_samples
from medical_evals.datasets.healthbench import load_healthbench_samples
from .evaluation_records import (
    deserialize_healthbench_record as _deserialize_healthbench_record,
    deserialize_medqa_record,
    healthbench_metrics,
    serialize_healthbench_result,
    serialize_medqa_result,
)
from .evaluation_sources import healthbench_samples_path


SAMPLE_MAX_RETRIES = 2


def _resolve_task_secret(encrypted_value: str, environment_name: str) -> str:
    """Prefer the encrypted task secret, with an optional env-name fallback."""
    if encrypted_value:
        return decrypt_secret(encrypted_value)
    return os.getenv(environment_name, "") if environment_name else ""


class _WorkbenchModelClient:
    """Adapt legacy injected Workbench fakes to the shared core protocol."""

    def __init__(self, client):
        self.client = client

    def complete(self, request: CompletionRequest, on_event=None) -> ModelResponse:
        if hasattr(self.client, "_complete_shared"):
            response = self.client.complete(request, on_event=on_event)
        else:
            try:
                response = self.client.complete(
                    request.prompt,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
            except Exception as error:
                if not hasattr(error, "retryable"):
                    setattr(error, "retryable", True)
                raise
        if isinstance(response, ModelResponse):
            return response
        return ModelResponse(
            text=str(response or ""),
            model=request.model,
            retry_count=int(getattr(self.client, "last_retry_count", 0)),
        )


@dataclass(frozen=True)
class EvaluationRunResult:
    success_count: int
    failed_count: int
    retry_count: int
    total_count: int
    total_score: float = 0.0
    dimension_scores: dict[str, float] | None = None
    error_categories: dict[str, int] | None = None
    accuracy: float = 0.0
    parse_success_rate: float | None = None
    request_success_count: int = 0
    parse_failed_count: int = 0
    samples: list[dict] | None = None


class EvaluationAdapter:
    def run(self, task: EvaluationTask | EvaluationRun, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult:
        raise NotImplementedError


class DryRunEvaluationAdapter(EvaluationAdapter):
    def run(self, task: EvaluationTask | EvaluationRun, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult:
        total = task.max_samples or task.progress.total_count or 1
        for completed in range(1, total + 1):
            if is_cancelled():
                break
            on_progress(TaskProgress(completed_count=completed, total_count=total, progress_percent=completed / total * 100, success_count=completed))
        return EvaluationRunResult(success_count=total, failed_count=0, retry_count=0, total_count=total)


class OpenAICompatibleEvaluationAdapter(EvaluationAdapter):
    def __init__(self, target_client=None, judge_client=None):
        self.target_client = target_client
        self.judge_client = judge_client
        self.on_sample = None
        self.on_log = None
        self.on_stage = None

    def _log(self, message: str) -> None:
        if message.startswith("[judge]"):
            self._stage("judge_model")
        elif message.startswith("[target]"):
            self._stage("target_model")
        elif message.startswith("[score]"):
            self._stage("scoring")
        if self.on_log:
            self.on_log(message)

    def _stage(self, name: str) -> None:
        if self.on_stage:
            self.on_stage(name)

    def _core_event(
        self,
        event: EvaluationEvent,
        *,
        sample_number: int,
        total_samples: int,
    ) -> None:
        log_stage = "target" if event.stage == "request" else event.stage
        if event.kind == "request_started":
            self._log(f"[{log_stage}] request started")
        elif event.kind == "request_completed":
            self._log(f"[{log_stage}] request completed")
        elif event.kind == "request_failed":
            self._log(f"[{log_stage}] request failed: {event.category or 'request_error'}")
        elif event.kind == "retry":
            self._log(
                f"[retry] sample {sample_number}/{total_samples} "
                f"attempt={event.attempt + 1} reason={event.category or 'request_error'}"
            )

    def run(self, task: EvaluationTask | EvaluationRun, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult:
        if task.dataset_version_id.startswith("medical-healthbench"):
            return self._run_healthbench(task, on_progress, is_cancelled)
        if not task.dataset_version_id.startswith("medical-medqa"):
            raise NotImplementedError("Unsupported dataset version")
        return self._run_medqa(task, on_progress, is_cancelled)

    def _run_medqa(self, task, on_progress, is_cancelled):
        samples = load_medqa_samples(registry_data_path("medical_medqa", "dev.jsonl"))
        if task.max_samples:
            samples = samples[:task.max_samples]
        checkpoint = getattr(self, "checkpoint", {})
        checkpoint_records = {
            index: record
            for index, record in checkpoint.items()
            if 0 <= index < len(samples)
        }
        sample_results_by_index = {
            index: deserialize_medqa_record(record)
            for index, record in checkpoint_records.items()
        }
        initial_summary = aggregate_medqa(
            [sample_results_by_index[index] for index in sorted(sample_results_by_index)]
        )
        on_progress(
            TaskProgress(
                completed_count=initial_summary.total_count,
                total_count=len(samples),
                progress_percent=(
                    initial_summary.total_count / len(samples) * 100
                    if samples
                    else 0
                ),
                success_count=initial_summary.success_count,
                failed_count=initial_summary.failed_count,
                retry_count=initial_summary.retry_count,
            )
        )
        target: ModelClient = cast(ModelClient, self.target_client or OpenAICompatibleClient(
            task.target_base_url,
            _resolve_task_secret(task.target_api_key_enc, task.target_api_key_env),
            max_retries=2,
            retry_base_seconds=1.0,
        ))
        success = initial_summary.success_count
        failed = initial_summary.failed_count
        total_retries = initial_summary.retry_count
        records_by_index = dict(checkpoint_records)
        for index, sample in enumerate(samples, start=1):
            if is_cancelled():
                break
            sample_index = index - 1
            if sample_index in checkpoint_records:
                continue
            self._log(f"[sample {index}/{len(samples)}] started")
            def on_event(event: EvaluationEvent, sample_number: int = index) -> None:
                self._core_event(
                    event,
                    sample_number=sample_number,
                    total_samples=len(samples),
                )

            result = evaluate_medqa_sample(
                target,
                sample,
                model=task.target_model_id,
                temperature=0.1,
                max_tokens=5120,
                on_event=on_event,
            )
            if result.error is None:
                self._stage("parsing")
                success += 1
            else:
                failed += 1
            total_retries += result.retry_count
            sample_results_by_index[sample_index] = result
            record = serialize_medqa_result(sample_index, sample, result)
            records_by_index[sample_index] = record
            if self.on_sample:
                self._stage("saving")
                self.on_sample(record)
            self._log(f"[sample {index}/{len(samples)}] {'completed' if not record.get('error') else 'failed'}")
            completed_count = len(sample_results_by_index)
            on_progress(
                TaskProgress(
                    completed_count=completed_count,
                    total_count=len(samples),
                    progress_percent=completed_count / len(samples) * 100 if samples else 0,
                    success_count=success,
                    failed_count=failed,
                    retry_count=total_retries,
                )
            )
        ordered_indexes = sorted(sample_results_by_index)
        summary = aggregate_medqa(
            [sample_results_by_index[index] for index in ordered_indexes]
        )
        return EvaluationRunResult(
            success_count=summary.success_count,
            failed_count=summary.failed_count,
            retry_count=summary.retry_count,
            total_count=len(samples),
            total_score=summary.total_score,
            dimension_scores=summary.dimensions,
            error_categories=summary.error_categories,
            accuracy=summary.total_score,
            parse_success_rate=summary.parse_success_rate,
            request_success_count=summary.request_success_count,
            parse_failed_count=summary.parse_failed_count,
            samples=[records_by_index[index] for index in ordered_indexes],
        )

    def _run_healthbench(self, task, on_progress, is_cancelled):
        path = healthbench_samples_path(task.dataset_version_id)
        samples = load_healthbench_samples(path)
        if task.max_samples:
            samples = samples[:task.max_samples]
        target = self.target_client or OpenAICompatibleClient(task.target_base_url, _resolve_task_secret(task.target_api_key_enc, task.target_api_key_env))
        judge = self.judge_client or OpenAICompatibleClient(task.judge_base_url, _resolve_task_secret(task.judge_api_key_enc, task.judge_api_key_env))
        target_core = _WorkbenchModelClient(target)
        judge_core = _WorkbenchModelClient(judge)
        checkpoint = getattr(self, "checkpoint", {})
        results_by_index: dict[int, HealthBenchSampleResult] = {}
        records_by_index: dict[int, dict] = {}
        for checkpoint_index, record in checkpoint.items():
            if 0 <= checkpoint_index < len(samples):
                result = _deserialize_healthbench_record(record)
                results_by_index[checkpoint_index] = result
                records_by_index[checkpoint_index] = record
        initial = aggregate_healthbench(list(results_by_index.values()))
        on_progress(TaskProgress(
            completed_count=len(results_by_index),
            total_count=len(samples),
            progress_percent=len(results_by_index) / len(samples) * 100 if samples else 0,
            success_count=initial.success_count,
            failed_count=initial.failed_count,
            retry_count=initial.retry_count,
        ))
        for index, sample in enumerate(samples, start=1):
            sample_index = index - 1
            if is_cancelled():
                break
            if sample_index in checkpoint:
                continue
            self._log(f"[sample {index}/{len(samples)}] started")
            self._stage("target_model")
            result = evaluate_healthbench_sample(
                target_core,
                judge_core,
                sample,
                target_model=task.target_model_id,
                judge_model=task.judge_model_id,
                on_event=lambda event, sample_number=index: self._core_event(
                    event, sample_number=sample_number, total_samples=len(samples)
                ),
            )
            results_by_index[sample_index] = result
            record = serialize_healthbench_result(sample_index, sample, result)
            records_by_index[sample_index] = record
            if result.error is None:
                self._log(f"[score] sample_score={result.score or 0.0:.4f}")
            if self.on_sample:
                self._stage("saving")
                self.on_sample(record)
            self._log(f"[sample {index}/{len(samples)}] {'completed' if result.error is None else 'failed'}")
            current = aggregate_healthbench(list(results_by_index.values()))
            on_progress(TaskProgress(
                completed_count=len(results_by_index), total_count=len(samples),
                progress_percent=len(results_by_index) / len(samples) * 100 if samples else 0,
                success_count=current.success_count, failed_count=current.failed_count,
                retry_count=current.retry_count,
            ))
        summary = aggregate_healthbench(list(results_by_index.values()))
        return EvaluationRunResult(
            success_count=summary.success_count,
            failed_count=summary.failed_count,
            retry_count=summary.retry_count,
            total_count=len(samples),
            total_score=summary.total_score,
            dimension_scores=summary.dimensions,
            error_categories=summary.error_categories,
            accuracy=summary.total_score,
            request_success_count=summary.request_success_count,
            samples=[records_by_index[index] for index in sorted(records_by_index)],
        )
