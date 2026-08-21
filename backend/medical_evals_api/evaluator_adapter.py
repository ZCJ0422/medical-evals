from collections.abc import Callable
from dataclasses import dataclass
import time

from .models import EvaluationTask
from .schemas.common import TaskProgress
from .openai_compatible import OpenAICompatibleClient
from .paths import registry_data_path, workspace_dataset_path
from .secrets import decrypt_secret
from medical_evals.core.medqa import (
    aggregate_medqa,
    evaluate_medqa_sample,
    make_safe_medqa_error,
)
from medical_evals.core.healthbench import (
    aggregate_healthbench,
    evaluate_healthbench_sample,
    make_safe_healthbench_error,
)
from medical_evals.core.models import CompletionRequest, EvaluationEvent, HealthBenchSampleResult, MedQASampleResult, ModelResponse
from medical_evals.datasets.medqa import load_medqa_samples
from medical_evals.datasets.healthbench import load_healthbench_samples


SAMPLE_MAX_RETRIES = 2


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
                    error.retryable = True
                raise
        if isinstance(response, ModelResponse):
            return response
        return ModelResponse(
            text=str(response or ""),
            model=request.model,
            retry_count=int(getattr(self.client, "last_retry_count", 0)),
        )


def serialize_medqa_result(
    index: int, sample: dict, result: MedQASampleResult
) -> dict:
    """Convert a shared MedQA result to the stable Workbench artifact schema."""
    error = result.error
    record = {
        "index": index,
        "sample_id": result.sample_id or str(sample.get("id", index)),
        "question": sample["question"],
        "expected": result.expected,
        "predicted": result.predicted,
        "correct": result.correct,
        "parse_failed": result.parse_failed,
        "raw_output": result.raw_output,
        "error": None,
        "error_category": None,
        "retry_count": result.retry_count,
    }
    if error is not None:
        safe_error = make_safe_medqa_error(
            category=error.category,
            stage=error.stage,
            retry_count=error.retry_count,
            status_code=error.status_code,
            attempt=error.attempt,
        )
        record.update(
            {
                "error": safe_error.message,
                "error_category": safe_error.category,
                "error_stage": safe_error.stage,
                "error_status_code": safe_error.status_code,
                "error_attempt": safe_error.attempt,
            }
        )
    return record


def deserialize_medqa_record(record: dict) -> MedQASampleResult:
    """Restore a Workbench checkpoint record for shared MedQA aggregation."""
    retry_count = int(record.get("retry_count", 0))
    error_message = record.get("error")
    error = None
    if error_message:
        error = make_safe_medqa_error(
            category=str(record.get("error_category") or "request_error"),
            retry_count=retry_count,
            stage=record.get("error_stage", "request"),
            status_code=record.get("error_status_code"),
            attempt=record.get("error_attempt"),
        )
    predicted = record.get("predicted")
    expected = str(record.get("expected", ""))
    return MedQASampleResult(
        sample_id=str(record.get("sample_id", "")),
        expected=expected,
        predicted=str(predicted) if predicted is not None else None,
        raw_output=str(record.get("raw_output", "")),
        correct=bool(record.get("correct", predicted == expected)),
        parse_failed=bool(record.get("parse_failed", False)),
        retry_count=retry_count,
        error=error,
    )


def healthbench_metrics(records: list[dict]) -> dict[str, object]:
    """Compatibility view over the shared HealthBench aggregation core."""
    summary = aggregate_healthbench([_deserialize_healthbench_record(record) for record in records])
    return {
        "score": summary.total_score,
        "tag_scores": {
            key.removeprefix("tag:"): value
            for key, value in summary.dimensions.items()
            if key.startswith("tag:")
        },
        "completed": summary.success_count,
        "failed": summary.failed_count,
    }
def healthbench_samples_path(dataset_version_id: str):
    """Resolve a HealthBench version to the data file it actually represents."""
    sources = {
        "medical-healthbench.smoke.v1": registry_data_path("medical_healthbench", "smoke.jsonl"),
        "medical-healthbench.oss.v1": workspace_dataset_path("HealthBench", "2025-05-07-06-14-12_oss_eval.jsonl"),
        "medical-healthbench.hard.v1": workspace_dataset_path("HealthBench", "hard_2025-05-08-21-00-10.jsonl"),
        "medical-healthbench.consensus.v1": workspace_dataset_path("HealthBench", "consensus_2025-05-09-20-00-46.jsonl"),
    }
    try:
        return sources[dataset_version_id]
    except KeyError as error:
        raise ValueError(f"Unsupported HealthBench dataset version: {dataset_version_id}") from error


def serialize_healthbench_result(index: int, sample: dict, result: HealthBenchSampleResult) -> dict:
    error = result.error
    return {
        "index": index,
        "sample_id": result.sample_id,
        # Keep the canonical sample-record fields aligned with MedQA and the UI.
        # The legacy HealthBench names remain below for existing artifacts.
        "raw_output": result.raw_output,
        "rubric_judgments": list(result.rubric_judgments),
        "predicted": result.raw_output,
        "rubric_results": list(result.rubric_judgments),
        "achieved": result.achieved,
        "positive_max": result.positive_max,
        "score": result.score,
        "tag_scores": result.tag_scores,
        "error": error.message if error else None,
        "error_category": error.category if error else None,
        "error_stage": error.stage if error else None,
        "error_status_code": error.status_code if error else None,
        "error_attempt": error.attempt if error else None,
        "retry_count": result.retry_count,
    }


def _deserialize_healthbench_record(record: dict) -> HealthBenchSampleResult:
    error = None
    if record.get("error"):
        error = make_safe_healthbench_error(
            category=str(record.get("error_category") or "request_error"),
            stage=str(record.get("error_stage") or "target"),
            retry_count=int(record.get("retry_count", 0)),
            status_code=record.get("error_status_code"),
            attempt=record.get("error_attempt"),
        )
    return HealthBenchSampleResult(
        sample_id=str(record.get("sample_id", "")),
        raw_output=str(record.get("raw_output", record.get("predicted", ""))),
        rubric_judgments=tuple(record.get("rubric_judgments", record.get("rubric_results", []))),
        score=record.get("score"),
        achieved=record.get("achieved"),
        positive_max=record.get("positive_max"),
        tag_scores=dict(record.get("tag_scores", {})),
        retry_count=int(record.get("retry_count", 0)),
        error=error,
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
    def run(self, task: EvaluationTask, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult:
        raise NotImplementedError


class DryRunEvaluationAdapter(EvaluationAdapter):
    def run(self, task: EvaluationTask, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult:
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

    def run(self, task: EvaluationTask, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult:
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
        target = self.target_client or OpenAICompatibleClient(
            task.target_base_url,
            decrypt_secret(task.target_api_key_enc),
            max_retries=2,
            retry_base_seconds=1.0,
        )
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
            result = evaluate_medqa_sample(
                target,
                sample,
                model=task.target_model_id,
                temperature=0.1,
                max_tokens=5120,
                on_event=lambda event, sample_number=index: self._core_event(
                    event,
                    sample_number=sample_number,
                    total_samples=len(samples),
                ),
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
        target = self.target_client or OpenAICompatibleClient(task.target_base_url, decrypt_secret(task.target_api_key_enc))
        judge = self.judge_client or OpenAICompatibleClient(task.judge_base_url, decrypt_secret(task.judge_api_key_enc))
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
