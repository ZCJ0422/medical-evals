from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..auth import AdminIdentity, require_admin
from ..config import settings
from ..repositories.tasks import TaskRepository
from ..services.reports import ReportService

router = APIRouter(prefix="/api/evaluations", tags=["reports"])


@router.post("/{task_id}/report/generate")
def generate_report(task_id: str, _: AdminIdentity = Depends(require_admin)):
    try:
        path = ReportService(TaskRepository(settings.database_path, settings.artifact_dir), settings.artifact_dir).generate_html(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Evaluation task not found") from exc
    return {"task_id": task_id, "format": "html", "path": str(path)}


@router.get("/{task_id}/report")
def get_report(task_id: str, _: AdminIdentity = Depends(require_admin)):
    path = settings.artifact_dir / task_id / "report.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not generated")
    return FileResponse(path, media_type="text/html")
