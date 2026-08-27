from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..auth import AdminIdentity, CurrentUser, require_admin
from ..config import settings
from ..database import get_session
from ..repositories.evaluations import EvaluationRepository
from ..repositories.tasks import TaskRepository
from ..schemas.common import ApiError
from ..schemas.results import (
    EvaluationArtifactResponse,
    EvaluationArtifactsResponse,
)
from ..services.reports import ReportService
from .evaluations import _visible_run, evaluation_repository

router = APIRouter(prefix="/api/evaluations", tags=["reports"])
v1_router = APIRouter(prefix="/api/v1/evaluations", tags=["reports"])

_ARTIFACT_KINDS = {
    "report.html": "report",
    "run.log": "log",
    "summary.json": "summary",
    "metadata.json": "metadata",
    "samples.jsonl": "samples",
}


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


def _artifact_directory(run_id: str) -> Path:
    return settings.artifact_dir / run_id


def _artifact_entries(run_id: str) -> list[EvaluationArtifactResponse]:
    directory = _artifact_directory(run_id)
    if not directory.exists():
        return []
    entries: list[EvaluationArtifactResponse] = []
    for name, kind in _ARTIFACT_KINDS.items():
        path = directory / name
        if not path.is_file():
            continue
        stats = path.stat()
        entries.append(
            EvaluationArtifactResponse(
                name=name,
                kind=kind,
                size_bytes=stats.st_size,
                updated_at=datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc),
                download_url=f"/api/v1/evaluations/{run_id}/artifacts/{name}",
            )
        )
    return entries


def _artifact_path(run_id: str, artifact_name: str) -> Path:
    if artifact_name not in _ARTIFACT_KINDS:
        raise ApiError(404, "artifact_not_found", "Artifact not found")
    path = _artifact_directory(run_id) / artifact_name
    if not path.is_file():
        raise ApiError(404, "artifact_not_found", "Artifact not found")
    return path


@router.post("/{task_id}/report/generate")
def generate_report(
    task_id: str,
    _: AdminIdentity = Depends(require_admin),
):
    repository, session = _resolve_repository(task_id)
    try:
        path = ReportService(repository, settings.artifact_dir).generate_html(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Evaluation task not found") from exc
    finally:
        if session is not None:
            session.close()
    return {"task_id": task_id, "format": "html", "path": str(path)}


@router.get("/{task_id}/report")
def get_report(
    task_id: str,
    _: AdminIdentity = Depends(require_admin),
):
    repository, session = _resolve_repository(task_id)
    try:
        if repository.get(task_id) is None:
            raise HTTPException(status_code=404, detail="Evaluation task not found")
    finally:
        if session is not None:
            session.close()
    path = settings.artifact_dir / task_id / "report.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not generated")
    return FileResponse(path, media_type="text/html")


@v1_router.get("/{run_id}/artifacts", response_model=EvaluationArtifactsResponse)
def list_artifacts_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationArtifactsResponse:
    repo = evaluation_repository(session)
    run = _visible_run(repo, run_id, user)
    if run is None:
        raise ApiError(404, "evaluation_run_not_found", "Evaluation run not found")
    return EvaluationArtifactsResponse(run_id=run.run_id, artifacts=_artifact_entries(run.run_id))


@v1_router.get("/{run_id}/artifacts/{artifact_name}")
def download_artifact_v1(
    run_id: str,
    artifact_name: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
):
    repo = evaluation_repository(session)
    run = _visible_run(repo, run_id, user)
    if run is None:
        raise ApiError(404, "evaluation_run_not_found", "Evaluation run not found")
    path = _artifact_path(run.run_id, artifact_name)
    media_type = "text/html" if artifact_name.endswith(".html") else "text/plain"
    return FileResponse(path, media_type=media_type, filename=artifact_name)
