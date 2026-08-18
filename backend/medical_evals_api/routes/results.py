from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..auth import AdminIdentity, require_admin
from ..artifacts import artifact_root_for_database
from ..config import settings
from ..repositories.tasks import TaskRepository
from ..services.results import ResultService

router = APIRouter(prefix="/api/evaluations", tags=["results"])


class EvaluationSummaryResponse(BaseModel):
    task_id: str
    name: str
    status: str
    dataset_version_id: str
    target_model_id: str
    judge_model_id: str
    created_at: str
    updated_at: str
    error: str | None
    stage: str
    progress_percent: float
    total_score: float
    dimension_scores: dict[str, float]
    accuracy: float
    parse_success_rate: float | None
    request_success_count: int
    parse_failed_count: int
    error_categories: dict[str, int]
    completed_count: int
    failed_count: int
    retry_count: int


@router.get("/{task_id}/results", response_model=EvaluationSummaryResponse)
def results(task_id: str, _: AdminIdentity = Depends(require_admin)) -> EvaluationSummaryResponse:
    try:
        summary = ResultService(TaskRepository(settings.database_path)).get_public_summary(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Evaluation task not found") from exc
    return EvaluationSummaryResponse(**summary.__dict__)


class EvaluationSamplesResponse(BaseModel):
    task_id: str
    offset: int
    limit: int
    total: int
    samples: list[dict]


@router.get("/{task_id}/samples", response_model=EvaluationSamplesResponse)
def samples(task_id: str, offset: int = 0, limit: int = 50, _: AdminIdentity = Depends(require_admin)) -> EvaluationSamplesResponse:
    if offset < 0 or limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="Invalid pagination")
    try:
        values, total = TaskRepository(settings.database_path).get_samples(task_id, offset, limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Evaluation task not found") from exc
    return EvaluationSamplesResponse(task_id=task_id, offset=offset, limit=limit, total=total, samples=values)


@router.get("/{task_id}/log", response_class=PlainTextResponse)
def run_log(task_id: str, _: AdminIdentity = Depends(require_admin)) -> PlainTextResponse:
    repository = TaskRepository(settings.database_path)
    if repository.get(task_id) is None:
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    path = artifact_root_for_database(settings.database_path) / task_id / "run.log"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return PlainTextResponse(content=content)
