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
    "EventCallback",
    "classify_error",
    "classify_status_code",
    "is_retryable_error",
    "retry_delay_seconds",
]
