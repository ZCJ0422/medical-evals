from collections.abc import Callable
from dataclasses import dataclass
import time

from .models import EvaluationTask
from .schemas.common import TaskProgress
from .openai_compatible import OpenAICompatibleClient
from .paths import registry_data_path, workspace_dataset_path
from .secrets import decrypt_secret
from medical_evals.datasets.medqa import load_medqa_samples
from medical_evals.graders.choice_parser import parse_choice
from medical_evals.datasets.healthbench import load_healthbench_samples
from medical_evals.judges.rubric import build_rubric_judge_prompt, parse_rubric_judgment


SAMPLE_MAX_RETRIES = 2


def medqa_metrics(records: list[dict]) -> dict[str, float | int | None]:
    total = len(records)
    request_success = sum(1 for record in records if not record.get("error"))
    parsed = sum(1 for record in records if not record.get("parse_failed"))
    correct = sum(1 for record in records if record.get("correct", record.get("predicted") == record.get("expected")))
    return {
        "accuracy": correct / total if total else 0.0,
        "parse_success_rate": parsed / request_success if request_success else None,
        "request_success_count": request_success,
        "parse_failed_count": sum(1 for record in records if record.get("parse_failed")),
    }


def _healthbench_prompt(sample: dict) -> list[dict]:
    return [dict(message) for message in sample["prompt"]]


def _medqa_prompt(sample: dict) -> str:
    lines = ["请回答下面的医学单项选择题。", f"题目：{sample['question']}", "选项："]
    lines.extend(f"{key}. {sample['options'][key]}" for key in ("A", "B", "C", "D"))
    lines.extend(["要求：", "不要输出解释、推理过程、答案文字、标点符号、Markdown 或其他内容。", "请只输出一个选项字母（A、B、C 或 D）。"])
    return "\n".join(lines)


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

    def run(self, task: EvaluationTask, on_progress: Callable[[TaskProgress], None], is_cancelled: Callable[[], bool]) -> EvaluationRunResult:
        if task.dataset_version_id.startswith("medical-healthbench"):
            return self._run_healthbench(task, on_progress, is_cancelled)
        if not task.dataset_version_id.startswith("medical-medqa"):
            raise NotImplementedError("Unsupported dataset version")
        samples = load_medqa_samples(registry_data_path("medical_medqa", "dev.jsonl"))
        if task.max_samples:
            samples = samples[:task.max_samples]
        target = self.target_client or OpenAICompatibleClient(task.target_base_url, decrypt_secret(task.target_api_key_enc))
        success = failed = correct = 0
        records = []
        checkpoint = getattr(self, "checkpoint", {})
        for index, sample in enumerate(samples, start=1):
            if is_cancelled(): break
            if index - 1 in checkpoint:
                record = checkpoint[index - 1]
                records.append(record)
                success += 1
                correct += int(bool(record.get("correct")))
                on_progress(TaskProgress(completed_count=index, total_count=len(samples), progress_percent=index / len(samples) * 100, success_count=success, failed_count=failed, retry_count=sum(int(item.get("retry_count", 0)) for item in records)))
                continue
            prompt = _medqa_prompt(sample)
            try:
                self._log(f"[sample {index}/{len(samples)}] started")
                self._stage("target_model")
                self._log("[target] request started")
                # Reasoning models may spend most of their completion budget on
                # hidden/visible thinking before emitting the choice letter.
                # Keep the evaluator's original MedQA budget instead of
                # truncating the answer during reasoning.
                answer = target.complete(prompt, model=task.target_model_id, temperature=0.1, max_tokens=5120)
                self._log("[target] request completed")
                self._stage("parsing")
                picked = parse_choice(answer)
                success += 1
                if picked == sample["answer"]:
                    correct += 1
                record = {"index": index - 1, "sample_id": sample.get("id", str(index - 1)), "question": sample["question"], "expected": sample["answer"], "predicted": picked, "correct": picked == sample["answer"], "parse_failed": picked is None, "raw_output": answer, "error": None, "retry_count": 0}
            except Exception as error:
                self._log(f"[target] request failed: {_error_category(error)}")
                failed += 1
                record = {"index": index - 1, "sample_id": sample.get("id", str(index - 1)), "question": sample["question"], "expected": sample["answer"], "predicted": None, "correct": False, "parse_failed": True, "raw_output": "", "error": str(error), "retry_count": 0}
            records.append(record)
            if self.on_sample:
                self._stage("saving")
                self.on_sample(record)
            self._log(f"[sample {index}/{len(samples)}] {'completed' if not record.get('error') else 'failed'}")
            on_progress(TaskProgress(completed_count=index, total_count=len(samples), progress_percent=index / len(samples) * 100, success_count=success, failed_count=failed))
        metrics = medqa_metrics(records)
        score = metrics["accuracy"]
        return EvaluationRunResult(success_count=success, failed_count=failed, retry_count=0, total_count=len(samples), total_score=score, dimension_scores={"accuracy": score}, error_categories={"request_error": failed} if failed else {}, accuracy=score, parse_success_rate=metrics["parse_success_rate"], request_success_count=success, parse_failed_count=metrics["parse_failed_count"], samples=records)

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
