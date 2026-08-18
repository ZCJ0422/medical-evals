from dataclasses import dataclass
from datetime import datetime, timezone

from .schemas.common import TaskProgress, TaskStatus


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EvaluationTask:
    task_id: str
    name: str
    target_model_id: str
    judge_model_id: str
    dataset_version_id: str
    rubric_id: str
    status: TaskStatus
    progress: TaskProgress
    created_at: str
    updated_at: str
    error: str | None = None
    target_base_url: str = ""
    target_api_key_enc: str = ""
    judge_base_url: str = ""
    judge_api_key_enc: str = ""
    max_samples: int | None = None
