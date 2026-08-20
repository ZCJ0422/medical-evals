"""Shared MedQA prompting, scoring, and error normalization."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from medical_evals.datasets.medqa import OPTION_KEYS
from medical_evals.graders.choice_parser import parse_choice

from .models import (
    CompletionRequest,
    EvaluationSummary,
    MedQASampleResult,
    SampleError,
)
from .protocols import EventCallback, ModelClient
from .retry import classify_error


def build_medqa_prompt(sample: dict) -> str:
    """Build the canonical MedQA prompt without exposing the answer."""
    lines = [
        "请回答下面的医学单项选择题。",
        f"题目：{sample['question']}",
        "选项：",
    ]
    lines.extend(f"{key}. {sample['options'][key]}" for key in OPTION_KEYS)
    lines.extend(
        [
            "要求：",
            "不要输出解释、推理过程、答案文字、标点符号、Markdown 或其他内容。",
            "请只输出一个选项字母（A、B、C 或 D）。",
        ]
    )
    return "\n".join(lines)


def evaluate_medqa_sample(
    client: ModelClient,
    sample: dict,
    *,
    model: str,
    temperature: float = 0.1,
    max_tokens: int = 5120,
    on_event: EventCallback | None = None,
) -> MedQASampleResult:
    """Evaluate one MedQA sample without allowing request errors to escape."""
    retry_events = 0

    def collect_event(event) -> None:
        nonlocal retry_events
        if event.kind == "retry":
            retry_events += 1
        if on_event is not None:
            on_event(event)

    expected = str(sample["answer"])
    sample_id = str(sample.get("id", ""))
    try:
        response = client.complete(
            CompletionRequest(
                prompt=build_medqa_prompt(sample),
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            on_event=collect_event,
        )
    except Exception as error:
        category, _ = classify_error(error)
        return MedQASampleResult(
            sample_id=sample_id,
            expected=expected,
            predicted=None,
            raw_output="",
            correct=False,
            parse_failed=False,
            retry_count=retry_events,
            error=SampleError(
                category=category,
                message=str(error),
                stage="request",
                retry_count=retry_events,
            ),
        )

    predicted = parse_choice(response.text)
    return MedQASampleResult(
        sample_id=sample_id,
        expected=expected,
        predicted=predicted,
        raw_output=response.text,
        correct=predicted == expected,
        parse_failed=predicted is None,
        retry_count=retry_events or response.retry_count,
    )


def aggregate_medqa(results: Sequence[MedQASampleResult]) -> EvaluationSummary:
    """Aggregate MedQA results with request and parse failures kept distinct."""
    total_count = len(results)
    failed_results = [result for result in results if result.error is not None]
    request_successes = [result for result in results if result.error is None]
    parse_failed_count = sum(result.parse_failed for result in request_successes)
    accuracy = sum(result.correct for result in results) / total_count if total_count else 0.0
    parse_success_rate = (
        (len(request_successes) - parse_failed_count) / len(request_successes)
        if request_successes
        else 0.0
    )
    error_categories = Counter(
        result.error.category for result in failed_results if result.error is not None
    )
    return EvaluationSummary(
        total_count=total_count,
        success_count=len(request_successes),
        failed_count=len(failed_results),
        retry_count=sum(result.retry_count for result in results),
        total_score=accuracy,
        dimensions={"accuracy": accuracy},
        request_success_count=len(request_successes),
        parse_failed_count=parse_failed_count,
        parse_success_rate=parse_success_rate,
        error_categories=dict(error_categories),
    )
