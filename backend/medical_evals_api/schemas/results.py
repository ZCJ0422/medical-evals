from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .evaluations import EvaluationRunStatus
from .common import TaskProgress


class EvaluationSummaryResponse(BaseModel):
    run_id: str
    name: str
    evaluation_definition_id: str
    dataset_version_id: str
    target_model_id: str
    judge_model_id: str
    status: EvaluationRunStatus
    progress: TaskProgress
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    total_score: float
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    accuracy: float
    parse_success_rate: float | None = None
    request_success_count: int
    parse_failed_count: int
    error_categories: dict[str, int] = Field(default_factory=dict)
    completed_count: int
    failed_count: int
    retry_count: int
    result_version: str = "workbench.result.v1"


class EvaluationSamplesResponse(BaseModel):
    run_id: str
    offset: int
    limit: int
    total: int
    has_more: bool
    samples: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationArtifactResponse(BaseModel):
    name: str
    kind: str
    size_bytes: int
    updated_at: datetime
    download_url: str


class EvaluationArtifactsResponse(BaseModel):
    run_id: str
    artifacts: list[EvaluationArtifactResponse] = Field(default_factory=list)
