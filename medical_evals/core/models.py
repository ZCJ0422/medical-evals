"""Immutable, entry-point-neutral values shared by evaluation adapters."""

from dataclasses import dataclass, field
from typing import Any

Prompt = str | list[dict[str, Any]]


@dataclass(frozen=True)
class CompletionRequest:
    prompt: Prompt
    model: str
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class EvaluationEvent:
    kind: str
    stage: str
    attempt: int = 1
    category: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model: str | None = None
    usage: dict[str, Any] | None = None
    usage_details: dict[str, Any] | None = None
    latency: float = 0.0
    retry_count: int = 0
    raw_response: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class SampleError:
    category: str
    message: str
    stage: str
    retry_count: int = 0


@dataclass(frozen=True)
class MedQASampleResult:
    sample_id: str
    expected: str
    predicted: str | None
    raw_output: str
    correct: bool
    parse_failed: bool
    retry_count: int
    error: SampleError | None = None


@dataclass(frozen=True)
class HealthBenchSampleResult:
    sample_id: str
    raw_output: str
    rubric_judgments: tuple[dict[str, Any], ...]
    score: float | None
    achieved: float | None
    positive_max: float | None
    tag_scores: dict[str, float]
    retry_count: int
    error: SampleError | None = None


@dataclass(frozen=True)
class EvaluationSummary:
    total_count: int
    success_count: int
    failed_count: int
    retry_count: int
    total_score: float
    dimensions: dict[str, float]
    request_success_count: int
    parse_failed_count: int = 0
    parse_success_rate: float | None = None
    error_categories: dict[str, int] = field(default_factory=dict)
