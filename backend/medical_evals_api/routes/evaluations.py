from datetime import datetime
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status as http_status
from sqlalchemy.orm import Session

from ..auth import AdminIdentity, CurrentUser, require_admin
from ..config import settings
from ..database import get_session
from ..models import EvaluationCreateCommand
from ..repositories.evaluations import EvaluationRepository
from ..repositories.tasks import TaskRepository
from ..queue import LocalTaskQueue
from ..schemas.common import ApiError, TaskStatus, TaskSummary
from ..schemas.evaluations import (
    EvaluationCreate,
    EvaluationRunCreate,
    EvaluationRunResponse,
    EvaluationRunStatus,
    PreflightResponse,
)
from ..secrets import encrypt_secret
from .catalog import DATASETS

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])
v1_router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])

_RETRY_SUFFIX = re.compile(r"\s-\sretry(\d*)$", re.IGNORECASE)
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DATASET_RUBRICS = {item.dataset_id: item.rubric_id for item in DATASETS}
_TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.PARTIAL_FAILED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}
_PUBLIC_STATUS_TO_INTERNAL = {
    EvaluationRunStatus.QUEUED: (TaskStatus.QUEUED.value,),
    EvaluationRunStatus.RUNNING: (TaskStatus.RUNNING.value,),
    EvaluationRunStatus.CANCELLED: (TaskStatus.CANCELLED.value,),
    EvaluationRunStatus.SUCCEEDED: (
        TaskStatus.COMPLETED.value,
        TaskStatus.PARTIAL_FAILED.value,
    ),
    EvaluationRunStatus.FAILED: (TaskStatus.FAILED.value,),
}


def _existing_runs_for_retry_name(repo, *, user_id: str | None = None):
    if user_id is not None and hasattr(repo, "list_owned"):
        return repo.list_owned(user_id)
    return repo.list()


def _retry_name(repo, name: str, *, user_id: str | None = None) -> str:
    """Create a numbered retry name, while normalizing legacy retry suffixes."""
    base_name = name
    while _RETRY_SUFFIX.search(base_name):
        base_name = _RETRY_SUFFIX.sub("", base_name)

    retry_number = 0
    for existing in _existing_runs_for_retry_name(repo, user_id=user_id):
        existing_base = existing.name
        existing_depth = 0
        while True:
            match = _RETRY_SUFFIX.search(existing_base)
            if match is None:
                break
            existing_depth = max(existing_depth + 1, int(match.group(1) or 0))
            existing_base = _RETRY_SUFFIX.sub("", existing_base)
        if existing_base == base_name:
            retry_number = max(retry_number, existing_depth)
    return f"{base_name} - retry{retry_number + 1}"


def repository() -> TaskRepository:
    return TaskRepository(settings.database_path, settings.artifact_dir)


def evaluation_repository(session: Session) -> EvaluationRepository:
    return EvaluationRepository(session, settings.artifact_dir)


def _summary(task) -> TaskSummary:
    return TaskSummary(
        task_id=task.task_id,
        name=task.name,
        target_model_id=task.target_model_id,
        judge_model_id=task.judge_model_id,
        dataset_version_id=task.dataset_version_id,
        status=task.status,
        progress=task.progress,
        created_at=task.created_at,
        updated_at=task.updated_at,
        error=task.error,
    )


def _public_status(status_value: TaskStatus) -> EvaluationRunStatus:
    if status_value in {TaskStatus.COMPLETED, TaskStatus.PARTIAL_FAILED}:
        return EvaluationRunStatus.SUCCEEDED
    if status_value == TaskStatus.FAILED:
        return EvaluationRunStatus.FAILED
    if status_value == TaskStatus.CANCELLED:
        return EvaluationRunStatus.CANCELLED
    if status_value == TaskStatus.RUNNING:
        return EvaluationRunStatus.RUNNING
    return EvaluationRunStatus.QUEUED


def _run_response(run) -> EvaluationRunResponse:
    return EvaluationRunResponse(
        run_id=run.run_id,
        name=run.name,
        evaluation_definition_id=run.evaluation_definition_id,
        target_model_id=run.target_model_id,
        judge_model_id=run.judge_model_id,
        dataset_version_id=run.dataset_version_id,
        status=_public_status(run.status),
        progress=run.progress,
        split=run.split,
        sample_limit=run.max_samples,
        config=run.config,
        created_at=run.created_at,
        updated_at=run.updated_at,
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        retry_of_run_id=run.retry_of_run_id,
        error=run.error,
    )


def _visible_run(repo: EvaluationRepository, run_id: str, user: CurrentUser):
    if user.role == "admin":
        return repo.get(run_id)
    return repo.get_owned(run_id, user.id)


def _visible_runs(
    repo: EvaluationRepository,
    user: CurrentUser,
    *,
    status_filter: EvaluationRunStatus | None,
    created_after: datetime | None,
    created_before: datetime | None,
    limit: int,
    offset: int,
):
    filters = {
        "status_values": _PUBLIC_STATUS_TO_INTERNAL[status_filter] if status_filter else None,
        "created_after": created_after,
        "created_before": created_before,
        "limit": limit,
        "offset": offset,
    }
    if user.role == "admin":
        return repo.list(filters)
    return repo.list_owned(user.id, filters)


def _enqueue_visible_run(repo: EvaluationRepository, run_id: str) -> None:
    LocalTaskQueue(repo).enqueue(run_id)


@router.post("/preflight", response_model=PreflightResponse)
def preflight(payload: EvaluationCreate, _: AdminIdentity = Depends(require_admin)) -> PreflightResponse:
    errors = []
    dataset = next((item for item in DATASETS if item.dataset_version_id == payload.dataset_version_id), None)
    if dataset is None:
        errors.append("Unsupported dataset version")
    else:
        expected_rubric = _DATASET_RUBRICS.get(dataset.dataset_id)
        if expected_rubric is None:
            errors.append("Unsupported dataset family")
        elif payload.rubric_id != expected_rubric:
            errors.append(f"Rubric must be {expected_rubric} for this dataset")
    if payload.target_api_key_env and not _ENV_NAME.fullmatch(payload.target_api_key_env):
        errors.append("Target API Key environment name is invalid")
    if payload.judge_api_key_env and not _ENV_NAME.fullmatch(payload.judge_api_key_env):
        errors.append("Judge API Key environment name is invalid")
    if not payload.target_api_key.strip() and not payload.target_api_key_env.strip():
        errors.append("Target API Key is required")
    target_url = urlparse(payload.target_base_url.strip())
    if target_url.scheme not in {"http", "https"} or not target_url.netloc:
        errors.append("Target Base URL must be a complete http:// or https:// URL")
    needs_judge = not payload.dataset_version_id.startswith("medical-medqa")
    if needs_judge and not payload.judge_model_id.strip():
        errors.append("This dataset requires a Judge Model configuration")
    if needs_judge and not payload.judge_api_key.strip() and not payload.judge_api_key_env.strip():
        errors.append("Judge API Key is required for this dataset")
    if needs_judge:
        judge_url = urlparse(payload.judge_base_url.strip())
        if judge_url.scheme not in {"http", "https"} or not judge_url.netloc:
            errors.append("Judge Base URL must be a complete http:// or https:// URL")
    if needs_judge and payload.target_model_id == payload.judge_model_id:
        errors.append("Target model and Judge Model must be different configurations")
    return PreflightResponse(
        ready=not errors,
        errors=errors,
        estimated_tokens=None,
        estimated_cost=None,
    )


@router.get("", response_model=list[TaskSummary])
def list_evaluations(_: AdminIdentity = Depends(require_admin)) -> list[TaskSummary]:
    return [_summary(task) for task in repository().list()]


@router.post("", response_model=TaskSummary, status_code=http_status.HTTP_201_CREATED)
def create_evaluation(payload: EvaluationCreate, _: AdminIdentity = Depends(require_admin)) -> TaskSummary:
    check = preflight(payload, _)
    if not check.ready:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=check.errors,
        )
    dataset = next((item for item in DATASETS if item.dataset_version_id == payload.dataset_version_id), None)
    dataset_name = dataset.name if dataset else payload.dataset_version_id.split(".")[0]
    generated_name = (
        f"{dataset_name}-{payload.target_model_id}-"
        f"{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S')}"
    )
    task = repository().create(
        name=payload.name.strip() or generated_name,
        target_model_id=payload.target_model_id,
        judge_model_id=payload.judge_model_id,
        dataset_version_id=payload.dataset_version_id,
        rubric_id=payload.rubric_id,
        target_base_url=payload.target_base_url,
        target_api_key_env=payload.target_api_key_env.strip(),
        target_api_key_enc=encrypt_secret(payload.target_api_key) if payload.target_api_key else "",
        judge_base_url=payload.judge_base_url,
        judge_api_key_env=payload.judge_api_key_env.strip(),
        judge_api_key_enc=encrypt_secret(payload.judge_api_key) if payload.judge_api_key else "",
        max_samples=payload.max_samples,
    )
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


@router.post("/{task_id}/retry", response_model=TaskSummary, status_code=http_status.HTTP_201_CREATED)
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
        target_api_key_env=task.target_api_key_env,
        target_api_key_enc=task.target_api_key_enc,
        judge_base_url=task.judge_base_url,
        judge_api_key_env=task.judge_api_key_env,
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


@router.delete("/{task_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_evaluation(task_id: str, _: AdminIdentity = Depends(require_admin)) -> Response:
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
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@v1_router.get("", response_model=list[EvaluationRunResponse])
def list_evaluations_v1(
    user: CurrentUser,
    session: Session = Depends(get_session),
    *,
    status_filter: EvaluationRunStatus | None = Query(default=None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> list[EvaluationRunResponse]:
    if offset < 0 or limit < 1 or limit > 200:
        raise ApiError(status_code=422, code="invalid_request", message="Invalid pagination")
    if (
        created_after is not None
        and created_before is not None
        and created_after > created_before
    ):
        raise ApiError(
            status_code=422,
            code="invalid_request",
            message="created_after must be earlier than created_before",
        )
    repo = evaluation_repository(session)
    runs = _visible_runs(
        repo,
        user,
        status_filter=status_filter,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return [_run_response(run) for run in runs]


@v1_router.post("", response_model=EvaluationRunResponse, status_code=http_status.HTTP_201_CREATED)
def create_evaluation_v1(
    payload: EvaluationRunCreate,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    repo = evaluation_repository(session)
    try:
        run = repo.create(
            user.id,
            EvaluationCreateCommand(
                name=payload.name,
                evaluation_definition_id=payload.evaluation_definition_id,
                target_model_profile_id=payload.target_model_id,
                judge_model_profile_id=payload.judge_model_id.strip() or None,
                split=payload.split,
                sample_limit=payload.sample_limit,
                config=dict(payload.config),
            ),
        )
    except ValueError as exc:
        raise ApiError(422, "invalid_evaluation_request", str(exc)) from exc
    except KeyError as exc:
        detail = {
            "evaluation_definition": "Evaluation definition not found",
            "split": "Evaluation split not found",
            "target_model": "Target model profile not found",
            "judge_model": "Judge model profile not found",
        }.get(str(exc.args[0]), "Evaluation could not be created")
        raise ApiError(404, "evaluation_dependency_not_found", detail) from exc
    _enqueue_visible_run(repo, run.run_id)
    return _run_response(run)


@v1_router.get("/{run_id}", response_model=EvaluationRunResponse)
def get_evaluation_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    run = _visible_run(evaluation_repository(session), run_id, user)
    if run is None:
        raise ApiError(404, "evaluation_run_not_found", "Evaluation run not found")
    return _run_response(run)


@v1_router.post("/{run_id}/cancel", response_model=EvaluationRunResponse)
def cancel_evaluation_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    repo = evaluation_repository(session)
    run = _visible_run(repo, run_id, user)
    if run is None:
        raise ApiError(404, "evaluation_run_not_found", "Evaluation run not found")
    if run.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
        raise ApiError(
            409,
            "invalid_state_transition",
            "Only queued or running evaluations can be cancelled",
        )
    return _run_response(repo.set_status(run_id, TaskStatus.CANCELLED))


@v1_router.post("/{run_id}/retry", response_model=EvaluationRunResponse, status_code=http_status.HTTP_201_CREATED)
def retry_evaluation_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    repo = evaluation_repository(session)
    run = _visible_run(repo, run_id, user)
    if run is None:
        raise ApiError(404, "evaluation_run_not_found", "Evaluation run not found")
    if run.status not in _TERMINAL_STATUSES:
        raise ApiError(
            409,
            "invalid_state_transition",
            "Only finished evaluations can be retried",
        )
    retried = repo.create(
        run.user_id,
        EvaluationCreateCommand(
            name=_retry_name(repo, run.name, user_id=run.user_id),
            evaluation_definition_id=run.evaluation_definition_id,
            target_model_profile_id=run.target_model_profile_id,
            judge_model_profile_id=run.judge_model_profile_id,
            split=run.split,
            sample_limit=run.max_samples,
            config=run.config,
            retry_of_run_id=run.run_id,
        ),
    )
    _enqueue_visible_run(repo, retried.run_id)
    return _run_response(retried)


@v1_router.delete("/{run_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_evaluation_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> Response:
    repo = evaluation_repository(session)
    run = _visible_run(repo, run_id, user)
    if run is None:
        raise ApiError(404, "evaluation_run_not_found", "Evaluation run not found")
    if run.status == TaskStatus.RUNNING:
        raise ApiError(
            409,
            "invalid_state_transition",
            "Cancel the running evaluation before deleting it",
        )
    if not repo.delete(run_id):
        raise ApiError(404, "evaluation_run_not_found", "Evaluation run not found")
    artifact_dir = settings.artifact_dir / run_id
    if artifact_dir.exists():
        import shutil

        shutil.rmtree(artifact_dir)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
