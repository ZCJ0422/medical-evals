from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

from ..auth import AdminIdentity, require_admin
from ..config import settings
from ..database import get_session
from ..repositories.evaluations import EvaluationRepository
from ..repositories.tasks import TaskRepository
from ..services.results import ResultService

router = APIRouter(prefix="/api/evaluations", tags=["results"])


def _resolve_repository(task_id: str):
    legacy = TaskRepository(settings.database_path, settings.artifact_dir)
    if legacy.get(task_id) is not None:
        return legacy, None
    session_gen = get_session(settings)
    session = next(session_gen)
    try:
        evaluation_repo = EvaluationRepository(session, settings.artifact_dir)
        if evaluation_repo.get(task_id) is not None:
            return evaluation_repo, session
    except OperationalError:
        session.close()
        return legacy, None
    session.close()
    return legacy, None


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
def results(
    task_id: str,
    _: AdminIdentity = Depends(require_admin),
) -> EvaluationSummaryResponse:
    repository, session = _resolve_repository(task_id)
    try:
        summary = ResultService(repository).get_public_summary(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Evaluation task not found") from exc
    finally:
        if session is not None:
            session.close()
    return EvaluationSummaryResponse(**summary.__dict__)


class EvaluationSamplesResponse(BaseModel):
    task_id: str
    offset: int
    limit: int
    total: int
    samples: list[dict]


@router.get("/{task_id}/samples", response_model=EvaluationSamplesResponse)
def samples(
    task_id: str,
    offset: int = 0,
    limit: int = 50,
    _: AdminIdentity = Depends(require_admin),
) -> EvaluationSamplesResponse:
    if offset < 0 or limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="Invalid pagination")
    repository, session = _resolve_repository(task_id)
    try:
        values, total = repository.get_samples(task_id, offset, limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Evaluation task not found") from exc
    finally:
        if session is not None:
            session.close()
    return EvaluationSamplesResponse(task_id=task_id, offset=offset, limit=limit, total=total, samples=values)


@router.get("/{task_id}/log", response_class=PlainTextResponse)
def run_log(
    task_id: str,
    _: AdminIdentity = Depends(require_admin),
) -> PlainTextResponse:
    repository, session = _resolve_repository(task_id)
    try:
        if repository.get(task_id) is None:
            raise HTTPException(status_code=404, detail="Evaluation task not found")
    finally:
        if session is not None:
            session.close()
    path = settings.artifact_dir / task_id / "run.log"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return PlainTextResponse(content=content)
