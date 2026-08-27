from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..schemas.common import TaskProgress, TaskStatus


@dataclass(frozen=True)
class EvaluationDefinitionSplit:
    id: str
    dataset_version_id: str
    version: str
    sample_count: int
    default_sample_limit: int
    rubric_id: str


@dataclass(frozen=True)
class EvaluationDefinition:
    id: str
    name: str
    kind: str
    requires_judge: bool
    default_config: dict[str, Any]
    splits: tuple[EvaluationDefinitionSplit, ...]


@dataclass(frozen=True)
class EvaluationCreateCommand:
    name: str
    evaluation_definition_id: str
    target_model_profile_id: str
    judge_model_profile_id: str | None
    split: str | None
    sample_limit: int | None
    config: dict[str, Any]
    retry_of_run_id: str | None = None


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    user_id: str
    name: str
    evaluation_definition_id: str
    target_model_profile_id: str
    judge_model_profile_id: str | None
    target_model_id: str
    judge_model_id: str
    dataset_version_id: str
    rubric_id: str
    status: TaskStatus
    progress: TaskProgress
    split: str
    max_samples: int | None
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    retry_of_run_id: str | None = None
    target_base_url: str = ""
    target_api_key_env: str = ""
    target_api_key_enc: str = ""
    judge_base_url: str = ""
    judge_api_key_env: str = ""
    judge_api_key_enc: str = ""
    lease_owner: str = ""
    lease_expires_at: datetime | None = None

    @property
    def task_id(self) -> str:
        return self.run_id
