from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..auth import AdminIdentity, require_admin
from ..artifacts import artifact_root_for_database
from ..config import settings
from ..repositories.tasks import TaskRepository
from ..services.reports import ReportService

router = APIRouter(prefix="/api/evaluations", tags=["reports"])


@router.post("/{task_id}/report/generate")
def generate_report(task_id: str, _: AdminIdentity = Depends(require_admin)):
    try:
        path = ReportService(TaskRepository(settings.database_path), artifact_root_for_database(settings.database_path)).generate_html(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Evaluation task not found") from exc
    return {"task_id": task_id, "format": "html", "path": str(path)}


@router.get("/{task_id}/report")
def get_report(task_id: str, _: AdminIdentity = Depends(require_admin)):
    path = artifact_root_for_database(settings.database_path) / task_id / "report.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not generated")
    return FileResponse(path, media_type="text/html")
