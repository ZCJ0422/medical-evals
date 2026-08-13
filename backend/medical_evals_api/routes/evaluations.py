from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import AdminIdentity, require_admin
from ..config import settings
from ..repositories.tasks import TaskRepository
from ..schemas.common import TaskStatus, TaskSummary
from ..schemas.evaluations import EvaluationCreate, PreflightResponse

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def repository() -> TaskRepository:
    return TaskRepository(settings.database_path)


def _summary(task) -> TaskSummary:
    return TaskSummary(task_id=task.task_id, name=task.name, target_model_id=task.target_model_id, judge_model_id=task.judge_model_id, dataset_version_id=task.dataset_version_id, status=task.status, progress=task.progress)


@router.post("/preflight", response_model=PreflightResponse)
def preflight(payload: EvaluationCreate, _: AdminIdentity = Depends(require_admin)) -> PreflightResponse:
    errors = []
    if payload.target_model_id == payload.judge_model_id:
        errors.append("Target model and Judge Model must be different configurations")
    return PreflightResponse(ready=not errors, errors=errors, estimated_tokens=None, estimated_cost=None)


@router.post("", response_model=TaskSummary, status_code=status.HTTP_201_CREATED)
def create_evaluation(payload: EvaluationCreate, _: AdminIdentity = Depends(require_admin)) -> TaskSummary:
    check = preflight(payload, _)
    if not check.ready:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=check.errors)
    task = repository().create(name=payload.name, target_model_id=payload.target_model_id, judge_model_id=payload.judge_model_id, dataset_version_id=payload.dataset_version_id, rubric_id=payload.rubric_id)
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
