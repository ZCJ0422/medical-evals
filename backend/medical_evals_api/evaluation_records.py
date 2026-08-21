"""Stable Workbench sample-record schemas and checkpoint conversions."""

from medical_evals.core.healthbench import (
    aggregate_healthbench,
    make_safe_healthbench_error,
)
from medical_evals.core.medqa import make_safe_medqa_error
from medical_evals.core.models import HealthBenchSampleResult, MedQASampleResult


def serialize_medqa_result(index: int, sample: dict, result: MedQASampleResult) -> dict:
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
    error = None
    if record.get("error"):
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


def serialize_healthbench_result(index: int, sample: dict, result: HealthBenchSampleResult) -> dict:
    """Convert a shared HealthBench result to the versioned sample schema."""
    error = result.error
    return {
        "index": index,
        "sample_id": result.sample_id,
        # Canonical names are shared with MedQA; legacy aliases preserve old artifacts.
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


def deserialize_healthbench_record(record: dict) -> HealthBenchSampleResult:
    """Restore a HealthBench checkpoint while preserving target/judge errors."""
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


def healthbench_metrics(records: list[dict]) -> dict[str, object]:
    """Compatibility view over the shared HealthBench aggregation core."""
    summary = aggregate_healthbench([deserialize_healthbench_record(record) for record in records])
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
