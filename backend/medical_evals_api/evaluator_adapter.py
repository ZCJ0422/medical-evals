from collections.abc import Callable
from dataclasses import dataclass
import time

from .models import EvaluationTask
from .schemas.common import TaskProgress
from .openai_compatible import OpenAICompatibleClient
from .paths import registry_data_path, workspace_dataset_path
from .secrets import decrypt_secret
from medical_evals.core.medqa import aggregate_medqa, evaluate_medqa_sample
from medical_evals.core.models import EvaluationEvent, MedQASampleResult, SampleError
from medical_evals.datasets.medqa import load_medqa_samples
from medical_evals.datasets.healthbench import load_healthbench_samples
from medical_evals.judges.rubric import build_rubric_judge_prompt, parse_rubric_judgment


SAMPLE_MAX_RETRIES = 2


def _healthbench_prompt(sample: dict) -> list[dict]:
    return [dict(message) for message in sample["prompt"]]


def serialize_medqa_result(
    index: int, sample: dict, result: MedQASampleResult
) -> dict:
    """Convert a shared MedQA result to the stable Workbench artifact schema."""
    error = result.error
    return {
        "index": index,
        "sample_id": result.sample_id or str(sample.get("id", index)),
        "question": sample["question"],
        "expected": result.expected,
        "predicted": result.predicted,
        "correct": result.correct,
        "parse_failed": result.parse_failed,
        "raw_output": result.raw_output,
        "error": error.message if error else None,
        "error_category": error.category if error else None,
        "retry_count": result.retry_count,
    }


def deserialize_medqa_record(record: dict) -> MedQASampleResult:
    """Restore a Workbench checkpoint record for shared MedQA aggregation."""
    retry_count = int(record.get("retry_count", 0))
    error_message = record.get("error")
    error = None
    if error_message:
        error = SampleError(
            category=str(record.get("error_category") or "request_error"),
            message=str(error_message),
            stage="request",
            retry_count=retry_count,
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


def _judge_healthbench_rubric(judge, sample: dict, answer: str, rubric: dict, model: str, on_event=None) -> dict:
    prompt = build_rubric_judge_prompt(sample["prompt"], answer, rubric["criterion"])
    for attempt in range(2):
        if on_event:
            on_event("[judge] request started")
        raw = judge.complete(prompt, model=model, temperature=0.0, max_tokens=5120)
        if on_event:
            on_event("[judge] request completed")
        try:
            return parse_rubric_judgment(raw)
        except ValueError:
            if on_event:
                on_event(f"[judge] result invalid (attempt {attempt + 1}/2)")
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")


def _healthbench_score_details(rubrics: list[dict], judgments: list[dict]) -> dict[str, float]:
    if len(rubrics) != len(judgments):
        raise ValueError("rubrics and judgments must have the same length")
    achieved = 0.0
    positive_max = 0.0
    for rubric, judgment in zip(rubrics, judgments):
        points = float(rubric["points"])
        if points > 0:
            positive_max += points
        if judgment.get("criteria_met") is True:
            achieved += points
    return {
        "achieved": achieved,
        "positive_max": positive_max,
        "score": achieved / positive_max if positive_max else 0.0,
    }


def _healthbench_tag_scores(rubrics: list[dict], judgments: list[dict]) -> dict[str, float]:
    grouped: dict[str, list[tuple[dict, dict]]] = {}
    for rubric, judgment in zip(rubrics, judgments):
        for tag in rubric.get("tags", []):
            grouped.setdefault(tag, []).append((rubric, judgment))
    return {
        tag: _healthbench_score_details(
            [item[0] for item in items], [item[1] for item in items]
        )["score"]
        for tag, items in grouped.items()
    }


def _evaluate_healthbench_sample(target, judge, sample: dict, target_model: str, judge_model: str, sample_index: int | None = None, on_event=None) -> tuple[dict, int]:
    """Evaluate one sample, retrying the complete target+judge flow on failure."""
    last_error: Exception | None = None
    for attempt in range(SAMPLE_MAX_RETRIES + 1):
        try:
            if on_event:
                on_event("[target] request started")
            answer = target.complete(_healthbench_prompt(sample), model=target_model, temperature=0.1, max_tokens=5120)
            if on_event:
                on_event("[target] request completed")
            judgments = [_judge_healthbench_rubric(judge, sample, answer, rubric, judge_model, on_event) for rubric in sample["rubrics"]]
            score_details = _healthbench_score_details(sample["rubrics"], judgments)
            tag_scores = _healthbench_tag_scores(sample["rubrics"], judgments)
            return {
                "raw_output": answer,
                "rubric_judgments": judgments,
                "score": score_details["score"],
                "achieved": score_details["achieved"],
                "positive_max": score_details["positive_max"],
                "tag_scores": tag_scores,
            }, attempt
        except Exception as error:
            last_error = error
            if attempt < SAMPLE_MAX_RETRIES:
                if on_event:
                    on_event(f"[retry] sample attempt={attempt + 2}/{SAMPLE_MAX_RETRIES + 1} reason={_error_category(error)}")
                time.sleep(2 ** attempt)
    raise last_error or RuntimeError("HealthBench sample evaluation failed")


def _aggregate_healthbench_scores(scores: list[float]) -> float:
    if not scores:
        return 0.0
    return min(1.0, max(0.0, sum(float(score) for score in scores) / len(scores)))


def healthbench_metrics(records: list[dict]) -> dict[str, object]:
    """Aggregate completed HealthBench samples using their rubric scores."""
    scored = [record for record in records if "score" in record]
    score = _aggregate_healthbench_scores([record["score"] for record in scored])
    tags = sorted({tag for record in scored for tag in record.get("tag_scores", {})})
    tag_scores = {
        tag: _aggregate_healthbench_scores(
            [record["tag_scores"][tag] for record in scored if tag in record.get("tag_scores", {})]
        )
        for tag in tags
    }
    return {
        "score": score,
        "tag_scores": tag_scores,
        "completed": len(scored),
        "failed": sum(1 for record in records if record.get("error")),
    }


def _error_category(error: Exception) -> str:
    message = str(error).lower()
    if "401" in message or "unauthorized" in message or "api key" in message:
        return "authentication_error"
    if "404" in message or "not found" in message:
        return "model_or_endpoint_error"
    if "nodename" in message or "connect" in message or "timeout" in message:
        return "network_error"
    return "request_error"


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
        if event.kind == "request_started":
            self._log("[target] request started")
        elif event.kind == "request_completed":
            self._log("[target] request completed")
        elif event.kind == "request_failed":
            self._log(f"[target] request failed: {event.category or 'request_error'}")
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
        target = self.target_client or OpenAICompatibleClient(
            task.target_base_url,
            decrypt_secret(task.target_api_key_enc),
            max_retries=2,
            retry_base_seconds=1.0,
        )
        success = failed = total_retries = 0
        records = []
        sample_results = []
        checkpoint = getattr(self, "checkpoint", {})
        for index, sample in enumerate(samples, start=1):
            if is_cancelled():
                break
            if index - 1 in checkpoint:
                record = checkpoint[index - 1]
                records.append(record)
                result = deserialize_medqa_record(record)
                sample_results.append(result)
                success += int(result.error is None)
                failed += int(result.error is not None)
                total_retries += result.retry_count
                on_progress(TaskProgress(completed_count=index, total_count=len(samples), progress_percent=index / len(samples) * 100, success_count=success, failed_count=failed, retry_count=total_retries))
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
            sample_results.append(result)
            record = serialize_medqa_result(index - 1, sample, result)
            records.append(record)
            if self.on_sample:
                self._stage("saving")
                self.on_sample(record)
            self._log(f"[sample {index}/{len(samples)}] {'completed' if not record.get('error') else 'failed'}")
            on_progress(TaskProgress(completed_count=index, total_count=len(samples), progress_percent=index / len(samples) * 100, success_count=success, failed_count=failed, retry_count=total_retries))
        summary = aggregate_medqa(sample_results)
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
            samples=records,
        )

    def _run_healthbench(self, task, on_progress, is_cancelled):
        path = healthbench_samples_path(task.dataset_version_id)
        samples = load_healthbench_samples(path)
        if task.max_samples:
            samples = samples[:task.max_samples]
        target = self.target_client or OpenAICompatibleClient(task.target_base_url, decrypt_secret(task.target_api_key_enc))
        judge = self.judge_client or OpenAICompatibleClient(task.judge_base_url, decrypt_secret(task.judge_api_key_enc))
        completed = failed = 0
        records = []
        error_categories = {}
        total_retries = 0
        checkpoint = getattr(self, "checkpoint", {})
        for index, sample in enumerate(samples, start=1):
            if is_cancelled(): break
            if index - 1 in checkpoint:
                record = checkpoint[index - 1]
                records.append(record)
                completed += 1
                total_retries += int(record.get("retry_count", 0))
                on_progress(TaskProgress(completed_count=index, total_count=len(samples), progress_percent=index / len(samples) * 100, success_count=completed, failed_count=failed, retry_count=total_retries))
                continue
            record = {"index": index - 1, "sample_id": sample["prompt_id"], "predicted": None, "correct": False, "parse_failed": False, "error": None, "retry_count": 0}
            try:
                self._log(f"[sample {index}/{len(samples)}] started")
                self._stage("target_model")
                result, retries = _evaluate_healthbench_sample(target, judge, sample, task.target_model_id, task.judge_model_id, index, self._log)
                total_retries += retries
                record.update(result, retry_count=retries)
                completed += 1
                self._log(f"[score] sample_score={result['score']:.4f}")
            except Exception as error:
                total_retries += SAMPLE_MAX_RETRIES
                failed += 1
                category = _error_category(error)
                error_categories[category] = error_categories.get(category, 0) + 1
                record.update({"raw_output": "", "error": str(error), "error_category": category, "retry_count": SAMPLE_MAX_RETRIES})
                self._log(f"[sample {index}/{len(samples)}] failed: {category}")
            records.append(record)
            if self.on_sample:
                self._stage("saving")
                self.on_sample(record)
            if not record.get("error"):
                self._log(f"[sample {index}/{len(samples)}] completed")
            on_progress(TaskProgress(completed_count=index, total_count=len(samples), progress_percent=index / len(samples) * 100, success_count=completed, failed_count=failed))
        metrics = healthbench_metrics(records)
        score = metrics["score"]
        dimensions = {"rubric_score": score}
        dimensions.update({f"tag:{tag}": tag_score for tag, tag_score in metrics["tag_scores"].items()})
        return EvaluationRunResult(success_count=completed, failed_count=failed, retry_count=total_retries, total_count=len(samples), total_score=score, dimension_scores=dimensions, error_categories=error_categories, accuracy=score, parse_success_rate=completed / len(samples) if samples else None, request_success_count=completed, samples=records)
