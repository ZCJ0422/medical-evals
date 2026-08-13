from enum import Enum

from pydantic import BaseModel, ConfigDict


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskProgress(BaseModel):
    completed_count: int = 0
    total_count: int = 0
    progress_percent: float = 0.0
    success_count: int = 0
    failed_count: int = 0
    retry_count: int = 0


class TaskSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    name: str
    target_model_id: str
    judge_model_id: str
    dataset_version_id: str
    status: TaskStatus
    progress: TaskProgress


class ProviderSummary(BaseModel):
    provider_id: str
    name: str


class ModelSummary(BaseModel):
    model_id: str
    provider_id: str
    name: str


class DatasetVersionSummary(BaseModel):
    dataset_version_id: str
    dataset_id: str
    name: str
    version: str
    sample_count: int


class RubricSummary(BaseModel):
    rubric_id: str
    name: str
    version: str
