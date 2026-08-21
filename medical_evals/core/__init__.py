"""Dependency-neutral contracts for shared medical evaluation behavior."""

from .models import (
    CompletionRequest,
    EvaluationEvent,
    EvaluationSummary,
    HealthBenchSampleResult,
    MedQASampleResult,
    ModelResponse,
    SampleError,
)
from .healthbench import (
    aggregate_healthbench,
    build_healthbench_prompt,
    build_rubric_judge_prompt,
    evaluate_healthbench_sample,
    make_safe_healthbench_error,
    parse_rubric_judgment,
)
from .protocols import EventCallback, ModelClient
from .retry import (
    classify_error,
    classify_status_code,
    is_retryable_error,
    retry_delay_seconds,
)

__all__ = [
    "CompletionRequest",
    "EvaluationEvent",
    "EvaluationSummary",
    "HealthBenchSampleResult",
    "MedQASampleResult",
    "ModelClient",
    "ModelResponse",
    "SampleError",
    "aggregate_healthbench",
    "build_healthbench_prompt",
    "build_rubric_judge_prompt",
    "evaluate_healthbench_sample",
    "make_safe_healthbench_error",
    "parse_rubric_judgment",
    "EventCallback",
    "classify_error",
    "classify_status_code",
    "is_retryable_error",
    "retry_delay_seconds",
]
