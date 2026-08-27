from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..auth import AdminIdentity, CurrentUser, require_admin
from ..config import settings
from ..database import get_session
from ..repositories.evaluations import EvaluationRepository
from ..repositories.tasks import TaskRepository
from ..schemas.common import ApiError
from ..schemas.results import EvaluationSamplesResponse, EvaluationSummaryResponse
from ..services.results import ResultService
from .evaluations import _public_status, _visible_run, evaluation_repository

router = APIRouter(prefix="/api/evaluations", tags=["results"])
v1_router = APIRouter(prefix="/api/v1/evaluations", tags=["results"])


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


class LegacyEvaluationSummaryResponse(BaseModel):
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


class LegacyEvaluationSamplesResponse(BaseModel):
    task_id: str
    offset: int
    limit: int
    total: int
    samples: list[dict]


def _summary_response(repo: EvaluationRepository, run_id: str) -> EvaluationSummaryResponse:
    run = repo.get(run_id)
    if run is None:
        raise KeyError(run_id)
    stored = repo.get_result(run_id) or {}
    return EvaluationSummaryResponse(
        run_id=run.run_id,
        name=run.name,
        evaluation_definition_id=run.evaluation_definition_id,
        dataset_version_id=run.dataset_version_id,
        target_model_id=run.target_model_id,
        judge_model_id=run.judge_model_id,
        status=_public_status(run.status),
        progress=run.progress,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        total_score=stored.get("total_score", 0.0),
        dimension_scores=dict(stored.get("dimension_scores", {})),
        accuracy=stored.get("accuracy", stored.get("total_score", 0.0)),
        parse_success_rate=stored.get("parse_success_rate"),
        request_success_count=stored.get("request_success_count", run.progress.success_count),
        parse_failed_count=stored.get("parse_failed_count", 0),
        error_categories=dict(stored.get("error_categories", {})),
        completed_count=stored.get("completed_count", run.progress.completed_count),
        failed_count=stored.get("failed_count", run.progress.failed_count),
        retry_count=stored.get("retry_count", run.progress.retry_count),
    )


@router.get("/{task_id}/results", response_model=LegacyEvaluationSummaryResponse)
def results(
    task_id: str,
    _: AdminIdentity = Depends(require_admin),
) -> LegacyEvaluationSummaryResponse:
    repository, session = _resolve_repository(task_id)
    try:
        summary = ResultService(repository).get_public_summary(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Evaluation task not found") from exc
    finally:
        if session is not None:
            session.close()
    return LegacyEvaluationSummaryResponse(**summary.__dict__)


@router.get("/{task_id}/samples", response_model=LegacyEvaluationSamplesResponse)
def samples(
    task_id: str,
    offset: int = 0,
    limit: int = 50,
    _: AdminIdentity = Depends(require_admin),
) -> LegacyEvaluationSamplesResponse:
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
    return LegacyEvaluationSamplesResponse(
        task_id=task_id,
        offset=offset,
        limit=limit,
        total=total,
        samples=values,
    )


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


@v1_router.get("/{run_id}/summary", response_model=EvaluationSummaryResponse)
def summary_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationSummaryResponse:
    repo = evaluation_repository(session)
    run = _visible_run(repo, run_id, user)
    if run is None:
        raise ApiError(404, "evaluation_run_not_found", "Evaluation run not found")
    return _summary_response(repo, run.run_id)


@v1_router.get("/{run_id}/samples", response_model=EvaluationSamplesResponse)
def samples_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
    *,
    offset: int = 0,
    limit: int = 50,
) -> EvaluationSamplesResponse:
    if offset < 0 or limit < 1 or limit > 200:
        raise ApiError(422, "invalid_request", "Invalid pagination")
    repo = evaluation_repository(session)
    run = _visible_run(repo, run_id, user)
    if run is None:
        raise ApiError(404, "evaluation_run_not_found", "Evaluation run not found")
    values, total = repo.get_samples(run.run_id, offset, limit)
    return EvaluationSamplesResponse(
        run_id=run.run_id,
        offset=offset,
        limit=limit,
        total=total,
        has_more=offset + len(values) < total,
        samples=values,
    )
