"""Shared HealthBench target, rubric-judge, and aggregation semantics."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .models import (
    CompletionRequest,
    EvaluationEvent,
    EvaluationSummary,
    HealthBenchSampleResult,
    SampleError,
)
from .retry import classify_error


def build_healthbench_prompt(sample: dict) -> list[dict]:
    return [dict(message) for message in sample["prompt"]]


def build_rubric_judge_prompt(prompt: list[dict], answer: str, criterion: str) -> list[dict]:
    conversation = json.dumps(prompt, ensure_ascii=False)
    return [
        {"role": "system", "content": (
            "You are a strict medical evaluation judge. Determine whether the candidate "
            "answer satisfies the single rubric criterion. Return only a JSON object with "
            "a boolean criteria_met and a concise explanation string."
        )},
        {"role": "user", "content": (
            f"Conversation: {conversation}\n\nCandidate answer:\n{answer}\n\n"
            f"Rubric criterion:\n{criterion}"
        )},
    ]


def parse_rubric_judgment(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("judge response must be a string")
    decoder = json.JSONDecoder()
    last_error: Exception | None = None
    for offset, character in enumerate(text.strip()):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text.strip(), offset)
        except json.JSONDecodeError as error:
            last_error = error
            continue
        if not isinstance(value, Mapping):
            continue
        criteria_met = value.get("criteria_met")
        explanation = value.get("explanation", "")
        if not isinstance(criteria_met, bool):
            raise ValueError("criteria_met must be a boolean")
        if explanation is None:
            explanation = ""
        if not isinstance(explanation, str):
            raise ValueError("explanation must be a string")
        return {"criteria_met": criteria_met, "explanation": explanation}
    raise ValueError(f"invalid judge JSON: {last_error or 'object not found'}")


def _safe_error(error: Exception, *, stage: str, retry_count: int = 0) -> SampleError:
    category, _ = classify_error(error)
    if stage == "judge" and isinstance(error, ValueError):
        category = "judge_parse_error"
    return SampleError(
        category=category,
        message=f"{stage} failed: {category}",
        stage=stage,
        retry_count=max(0, int(retry_count)),
        status_code=getattr(error, "status_code", None),
        attempt=max(1, int(retry_count) + 1),
    )


def _score_rubrics(rubrics: Sequence[dict], judgments: Sequence[dict]) -> dict[str, float]:
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


def _tag_scores(rubrics: Sequence[dict], judgments: Sequence[dict]) -> dict[str, float]:
    grouped: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for rubric, judgment in zip(rubrics, judgments):
        for tag in rubric.get("tags", []):
            grouped[tag].append((rubric, judgment))
    return {
        tag: _score_rubrics([item[0] for item in items], [item[1] for item in items])["score"]
        for tag, items in grouped.items()
    }


def evaluate_healthbench_sample(
    target,
    judge,
    sample: dict,
    *,
    target_model: str,
    judge_model: str,
    target_temperature: float = 0.1,
    target_max_tokens: int = 5120,
    judge_temperature: float = 0.0,
    judge_max_tokens: int = 5120,
    on_event=None,
) -> HealthBenchSampleResult:
    """Evaluate one sample; transport retries belong to the shared clients."""
    try:
        target_response = None
        total_retries = 0
        for target_attempt in range(3):
            try:
                if on_event:
                    on_event(EvaluationEvent("request_started", "target", attempt=target_attempt + 1, message="request started"))
                target_response = target.complete(CompletionRequest(
                    build_healthbench_prompt(sample), target_model, target_temperature, target_max_tokens
                ), on_event=on_event)
                break
            except Exception as target_error:
                category, retryable = classify_error(target_error)
                if target_attempt >= 2 or not retryable:
                    raise
                total_retries += 1
                if on_event:
                    on_event(EvaluationEvent("retry", "target", attempt=target_attempt + 1, category=category))
        if target_response is None:
            raise RuntimeError("target request failed")
        if on_event:
            on_event(EvaluationEvent("request_completed", "target", message="request completed"))
        answer = target_response.text
        total_retries += target_response.retry_count
        judgments: list[dict] = []
        for rubric in sample["rubrics"]:
            judge_error: Exception | None = None
            for attempt in range(2):
                try:
                    judge_response = judge.complete(CompletionRequest(
                        build_rubric_judge_prompt(sample["prompt"], answer, rubric["criterion"]),
                        judge_model, judge_temperature, judge_max_tokens,
                    ), on_event=on_event)
                    if on_event:
                        on_event(EvaluationEvent("request_completed", "judge", message="request completed"))
                    return_value = parse_rubric_judgment(judge_response.text)
                    total_retries += judge_response.retry_count
                    judge_error = None
                    break
                except ValueError as error:
                    judge_error = error
                    if on_event:
                        on_event(EvaluationEvent("parse_failed", "judge", attempt=attempt + 1, category="judge_parse_error"))
            if judge_error is not None:
                raise judge_error
            judgments.append({
                "criterion": rubric["criterion"],
                "points": rubric["points"],
                "tags": list(rubric.get("tags", [])),
                **return_value,
            })
        score = _score_rubrics(sample["rubrics"], judgments)
        return HealthBenchSampleResult(
            sample_id=str(sample["prompt_id"]),
            raw_output=answer,
            rubric_judgments=tuple(judgments),
            score=score["score"],
            achieved=score["achieved"],
            positive_max=score["positive_max"],
            tag_scores=_tag_scores(sample["rubrics"], judgments),
            retry_count=total_retries,
        )
    except Exception as error:
        stage = "judge" if "judge_error" in locals() and judge_error is not None else "target"
        return HealthBenchSampleResult(
            sample_id=str(sample["prompt_id"]),
            raw_output=locals().get("answer", ""),
            rubric_judgments=tuple(),
            score=None,
            achieved=None,
            positive_max=None,
            tag_scores={},
            retry_count=int(locals().get("total_retries", getattr(locals().get("target_response"), "retry_count", 0))),
            error=_safe_error(error, stage=stage),
        )


def aggregate_healthbench(results: Sequence[HealthBenchSampleResult]) -> EvaluationSummary:
    successful = [result for result in results if result.error is None and result.score is not None]
    overall = sum(float(result.score) for result in successful) / len(successful) if successful else 0.0
    tags = sorted({tag for result in successful for tag in result.tag_scores})
    dimensions = {"rubric_score": overall}
    for tag in tags:
        values = [result.tag_scores[tag] for result in successful if tag in result.tag_scores]
        dimensions[f"tag:{tag}"] = sum(values) / len(values) if values else 0.0
    errors: dict[str, int] = {}
    for result in results:
        if result.error:
            errors[result.error.category] = errors.get(result.error.category, 0) + 1
    return EvaluationSummary(
        total_count=len(results),
        success_count=len(successful),
        failed_count=len(results) - len(successful),
        retry_count=sum(result.retry_count for result in results),
        total_score=overall,
        dimensions=dimensions,
        request_success_count=sum(1 for result in results if result.error is None),
        error_categories=errors,
    )
