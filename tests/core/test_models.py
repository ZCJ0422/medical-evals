from dataclasses import FrozenInstanceError

import pytest

from medical_evals.core.models import (
    CompletionRequest,
    EvaluationEvent,
    EvaluationSummary,
    HealthBenchSampleResult,
    MedQASampleResult,
    ModelResponse,
    SampleError,
)


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


def test_core_contracts_are_immutable_and_keep_normalized_fields():
    request = CompletionRequest(
        prompt="question",
        model="model-a",
        temperature=0.1,
        max_tokens=5120,
    )
    error = SampleError(
        category="request_error",
        message="temporary failure",
        stage="target",
        retry_count=2,
    )
    medqa = MedQASampleResult(
        sample_id="medqa-1",
        expected="C",
        predicted=None,
        raw_output="",
        correct=False,
        parse_failed=True,
        retry_count=2,
        error=error,
    )
    healthbench = HealthBenchSampleResult(
        sample_id="healthbench-1",
        raw_output="answer",
        rubric_judgments=({"criteria_met": True},),
        score=1.0,
        achieved=1.0,
        positive_max=1.0,
        tag_scores={"safety": 1.0},
        retry_count=1,
    )
    summary = EvaluationSummary(
        total_count=2,
        success_count=1,
        failed_count=1,
        retry_count=3,
        total_score=0.5,
        dimensions={"accuracy": 0.5},
        request_success_count=1,
        parse_failed_count=1,
        parse_success_rate=0.0,
        error_categories={"request_error": 1},
    )
    event = EvaluationEvent(
        kind="retry",
        stage="target",
        attempt=2,
        category="request_error",
        message="temporary failure",
    )

    assert medqa.error == error
    assert healthbench.tag_scores == {"safety": 1.0}
    assert summary.error_categories == {"request_error": 1}
    assert event.attempt == 2

    with pytest.raises(FrozenInstanceError):
        request.model = "model-b"
