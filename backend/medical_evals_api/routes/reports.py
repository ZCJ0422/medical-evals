from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.exc import OperationalError

from ..auth import AdminIdentity, require_admin
from ..config import settings
from ..database import get_session
from ..repositories.evaluations import EvaluationRepository
from ..repositories.tasks import TaskRepository
from ..services.reports import ReportService

router = APIRouter(prefix="/api/evaluations", tags=["reports"])


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
