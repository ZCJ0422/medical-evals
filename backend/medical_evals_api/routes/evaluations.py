from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import AdminIdentity, require_admin
from ..config import settings
from ..repositories.tasks import TaskRepository
from ..schemas.common import TaskStatus, TaskSummary
from ..schemas.evaluations import EvaluationCreate, PreflightResponse
from ..secrets import encrypt_secret
from .catalog import DATASETS

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])

_RETRY_SUFFIX = re.compile(r"\s-\sretry(\d*)$", re.IGNORECASE)


def _retry_name(repo: TaskRepository, name: str) -> str:
    """Create a numbered retry name, while normalizing legacy retry suffixes."""
    base_name = name
    while _RETRY_SUFFIX.search(base_name):
        base_name = _RETRY_SUFFIX.sub("", base_name)

    retry_number = 0
    for existing in repo.list():
        existing_base = existing.name
        existing_depth = 0
        while _RETRY_SUFFIX.search(existing_base):
            match = _RETRY_SUFFIX.search(existing_base)
            existing_depth = max(existing_depth + 1, int(match.group(1) or 0))
            existing_base = _RETRY_SUFFIX.sub("", existing_base)
        if existing_base == base_name:
            retry_number = max(retry_number, existing_depth)
    return f"{base_name} - retry{retry_number + 1}"


def repository() -> TaskRepository:
    return TaskRepository(settings.database_path, settings.artifact_dir)


def _summary(task) -> TaskSummary:
    return TaskSummary(task_id=task.task_id, name=task.name, target_model_id=task.target_model_id, judge_model_id=task.judge_model_id, dataset_version_id=task.dataset_version_id, status=task.status, progress=task.progress, created_at=task.created_at, updated_at=task.updated_at, error=task.error)


@router.post("/preflight", response_model=PreflightResponse)
def preflight(payload: EvaluationCreate, _: AdminIdentity = Depends(require_admin)) -> PreflightResponse:
    errors = []
    if not payload.target_api_key.strip():
        errors.append("Target API Key is required")
    target_url = urlparse(payload.target_base_url.strip())
    if target_url.scheme not in {"http", "https"} or not target_url.netloc:
        errors.append("Target Base URL must be a complete http:// or https:// URL")
    needs_judge = not payload.dataset_version_id.startswith("medical-medqa")
    if needs_judge and not payload.judge_model_id.strip():
        errors.append("This dataset requires a Judge Model configuration")
    if needs_judge and not payload.judge_api_key.strip():
        errors.append("Judge API Key is required for this dataset")
    if needs_judge:
        judge_url = urlparse(payload.judge_base_url.strip())
        if judge_url.scheme not in {"http", "https"} or not judge_url.netloc:
            errors.append("Judge Base URL must be a complete http:// or https:// URL")
    if needs_judge and payload.target_model_id == payload.judge_model_id:
        errors.append("Target model and Judge Model must be different configurations")
    return PreflightResponse(ready=not errors, errors=errors, estimated_tokens=None, estimated_cost=None)


@router.get("", response_model=list[TaskSummary])
def list_evaluations(_: AdminIdentity = Depends(require_admin)) -> list[TaskSummary]:
    return [_summary(task) for task in repository().list()]


@router.post("", response_model=TaskSummary, status_code=status.HTTP_201_CREATED)
def create_evaluation(payload: EvaluationCreate, _: AdminIdentity = Depends(require_admin)) -> TaskSummary:
    check = preflight(payload, _)
    if not check.ready:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=check.errors)
    dataset = next((item for item in DATASETS if item.dataset_version_id == payload.dataset_version_id), None)
    dataset_name = dataset.name if dataset else payload.dataset_version_id.split(".")[0]
    generated_name = f"{dataset_name}-{payload.target_model_id}-{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S')}"
    task = repository().create(name=payload.name.strip() or generated_name, target_model_id=payload.target_model_id, judge_model_id=payload.judge_model_id, dataset_version_id=payload.dataset_version_id, rubric_id=payload.rubric_id, target_base_url=payload.target_base_url, target_api_key_enc=encrypt_secret(payload.target_api_key), judge_base_url=payload.judge_base_url, judge_api_key_enc=encrypt_secret(payload.judge_api_key) if payload.judge_api_key else "", max_samples=payload.max_samples)
    return _summary(task)


@router.get("/{task_id}", response_model=TaskSummary)
def get_evaluation(task_id: str, _: AdminIdentity = Depends(require_admin)) -> TaskSummary:
    task = repository().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    return _summary(task)


@router.get("/{task_id}/progress")
def get_progress(task_id: str, _: AdminIdentity = Depends(require_admin)):
    task = repository().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    return task.progress


@router.post("/{task_id}/cancel", response_model=TaskSummary)
def cancel_evaluation(task_id: str, _: AdminIdentity = Depends(require_admin)) -> TaskSummary:
    task = repository().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    if task.status.value in {"completed", "partial_failed", "failed", "cancelled"}:
        return _summary(task)
    return _summary(repository().set_status(task_id, TaskStatus.CANCELLED))


@router.post("/{task_id}/retry", response_model=TaskSummary, status_code=status.HTTP_201_CREATED)
def retry_evaluation(task_id: str, _: AdminIdentity = Depends(require_admin)) -> TaskSummary:
    repo = repository()
    task = repo.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    if task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Only finished evaluations can be retried")
    retried = repo.create(
        name=_retry_name(repo, task.name),
        target_model_id=task.target_model_id,
        judge_model_id=task.judge_model_id,
        dataset_version_id=task.dataset_version_id,
        rubric_id=task.rubric_id,
        target_base_url=task.target_base_url,
        target_api_key_enc=task.target_api_key_enc,
        judge_base_url=task.judge_base_url,
        judge_api_key_enc=task.judge_api_key_enc,
        max_samples=task.max_samples,
    )
    return _summary(retried)


@router.post("/{task_id}/resume", response_model=TaskSummary)
def resume_evaluation(task_id: str, _: AdminIdentity = Depends(require_admin)) -> TaskSummary:
    repo = repository()
    task = repo.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    if task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Evaluation is already active")
    if task.status == TaskStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Completed evaluations do not need to be resumed")
    return _summary(repo.set_status(task_id, TaskStatus.QUEUED))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evaluation(task_id: str, _: AdminIdentity = Depends(require_admin)) -> None:
    repo = repository()
    task = repo.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Cancel the running task before deleting it")
    if not repo.delete(task_id):
        raise HTTPException(status_code=404, detail="Evaluation task not found")
    artifact_dir = settings.artifact_dir / task_id
    if artifact_dir.exists():
        import shutil
        shutil.rmtree(artifact_dir)
