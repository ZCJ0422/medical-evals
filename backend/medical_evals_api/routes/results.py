from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import AdminIdentity, require_admin
from ..config import settings
from ..repositories.tasks import TaskRepository
from ..services.results import ResultService

router = APIRouter(prefix="/api/evaluations", tags=["results"])


class EvaluationSummaryResponse(BaseModel):
    task_id: str
    total_score: float
    dimension_scores: dict[str, float]
    pass_rate: float
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
