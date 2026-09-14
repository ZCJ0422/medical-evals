from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .common import TaskProgress, TaskStatus


class EvaluationCreate(BaseModel):
    name: str = Field(default="", max_length=120)
    target_model_id: str
    judge_model_id: str = ""
    dataset_version_id: str
    rubric_id: str
    target_base_url: str = ""
    target_api_key: str = ""
    target_api_key_env: str = Field(default="", max_length=128)
    judge_base_url: str = ""
    judge_api_key: str = ""
    judge_api_key_env: str = Field(default="", max_length=128)
    max_samples: int | None = Field(default=None, ge=1, le=10000)


class EvaluationDefinitionSplitResponse(BaseModel):
    id: str
    dataset_version_id: str
    version: str
    sample_count: int
    default_sample_limit: int
    source_path: str | None = None
    source_sha256: str | None = None


class EvaluationDefinitionResponse(BaseModel):
    id: str
    name: str
    requires_judge: bool
    splits: list[EvaluationDefinitionSplitResponse]
    default_split: str | None = None
    default_sample_limit: int | None = None
    judge_model_id: str | None = None


class EvaluationDefinitionConfigUpdate(BaseModel):
    default_split: str
    default_sample_limit: int = Field(ge=1, le=10000)
    judge_model_id: str | None = None


class EvaluationRunCreate(BaseModel):
    name: str = Field(default="", max_length=120)
    evaluation_definition_id: str
    target_model_id: str
    judge_model_id: str = ""
    split: str | None = None
    sample_limit: int | None = Field(default=None, ge=1, le=10000)
    config: dict[str, Any] = Field(default_factory=dict)


class EvaluationRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EvaluationRunResponse(BaseModel):
    run_id: str
    submitted_by: str | None = None
    name: str
    evaluation_definition_id: str
    target_model_id: str
    judge_model_id: str
    dataset_version_id: str
    status: EvaluationRunStatus
    progress: TaskProgress
    split: str
    sample_limit: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retry_of_run_id: str | None = None
    error: str | None = None


class PreflightResponse(BaseModel):
    ready: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_tokens: int | None = None
    estimated_cost: float | None = None
