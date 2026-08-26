from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import AdminIdentity, CurrentUser, require_admin
from ..config import settings
from ..database import get_session
from ..models import EvaluationCreateCommand
from ..repositories.evaluations import EvaluationRepository
from ..repositories.tasks import TaskRepository
from ..schemas.common import TaskStatus, TaskSummary
from ..schemas.evaluations import (
    EvaluationCreate,
    EvaluationRunCreate,
    EvaluationRunResponse,
    PreflightResponse,
)
from ..secrets import encrypt_secret
from .catalog import DATASETS

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])
v1_router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])

_RETRY_SUFFIX = re.compile(r"\s-\sretry(\d*)$", re.IGNORECASE)
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DATASET_RUBRICS = {item.dataset_id: item.rubric_id for item in DATASETS}


def _retry_name(repo: TaskRepository, name: str) -> str:
    """Create a numbered retry name, while normalizing legacy retry suffixes."""
    base_name = name
    while _RETRY_SUFFIX.search(base_name):
        base_name = _RETRY_SUFFIX.sub("", base_name)

    retry_number = 0
    for existing in repo.list():
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
    return TaskSummary(task_id=task.task_id, name=task.name, target_model_id=task.target_model_id, judge_model_id=task.judge_model_id, dataset_version_id=task.dataset_version_id, status=task.status, progress=task.progress, created_at=task.created_at, updated_at=task.updated_at, error=task.error)


def _run_response(run) -> EvaluationRunResponse:
    return EvaluationRunResponse(
        run_id=run.run_id,
        name=run.name,
        evaluation_definition_id=run.evaluation_definition_id,
        target_model_id=run.target_model_id,
        judge_model_id=run.judge_model_id,
        dataset_version_id=run.dataset_version_id,
        status=run.status,
        progress=run.progress,
        split=run.split,
        sample_limit=run.max_samples,
        config=run.config,
        created_at=run.created_at,
        updated_at=run.updated_at,
        error=run.error,
    )


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
    task = repository().create(name=payload.name.strip() or generated_name, target_model_id=payload.target_model_id, judge_model_id=payload.judge_model_id, dataset_version_id=payload.dataset_version_id, rubric_id=payload.rubric_id, target_base_url=payload.target_base_url, target_api_key_env=payload.target_api_key_env.strip(), target_api_key_enc=encrypt_secret(payload.target_api_key) if payload.target_api_key else "", judge_base_url=payload.judge_base_url, judge_api_key_env=payload.judge_api_key_env.strip(), judge_api_key_enc=encrypt_secret(payload.judge_api_key) if payload.judge_api_key else "", max_samples=payload.max_samples)
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


@v1_router.get("", response_model=list[EvaluationRunResponse])
def list_evaluations_v1(
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> list[EvaluationRunResponse]:
    repo = evaluation_repository(session)
    return [_run_response(run) for run in repo.list_owned(user.id)]


@v1_router.post("", response_model=EvaluationRunResponse, status_code=status.HTTP_201_CREATED)
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
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        detail = {
            "evaluation_definition": "Evaluation definition not found",
            "split": "Evaluation split not found",
            "target_model": "Target model profile not found",
            "judge_model": "Judge model profile not found",
        }.get(str(exc.args[0]), "Evaluation could not be created")
        raise HTTPException(status_code=404, detail=detail) from exc
    from ..queue import LocalTaskQueue

    LocalTaskQueue(repo).enqueue(run.run_id)
    return _run_response(run)


@v1_router.get("/{run_id}", response_model=EvaluationRunResponse)
def get_evaluation_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    run = evaluation_repository(session).get_owned(run_id, user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return _run_response(run)


@v1_router.post("/{run_id}/cancel", response_model=EvaluationRunResponse)
def cancel_evaluation_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    repo = evaluation_repository(session)
    run = repo.get_owned(run_id, user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    if run.status.value in {"completed", "partial_failed", "failed", "cancelled"}:
        return _run_response(run)
    return _run_response(repo.set_status(run_id, TaskStatus.CANCELLED))


@v1_router.post("/{run_id}/retry", response_model=EvaluationRunResponse, status_code=status.HTTP_201_CREATED)
def retry_evaluation_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    repo = evaluation_repository(session)
    run = repo.get_owned(run_id, user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    if run.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Only finished evaluations can be retried")
    retried = repo.create(
        user.id,
        EvaluationCreateCommand(
            name=_retry_name(repo, run.name),
            evaluation_definition_id=run.evaluation_definition_id,
            target_model_profile_id=run.target_model_profile_id,
            judge_model_profile_id=run.judge_model_profile_id,
            split=run.split,
            sample_limit=run.max_samples,
            config=run.config,
            retry_of_run_id=run.run_id,
        ),
    )
    from ..queue import LocalTaskQueue

    LocalTaskQueue(repo).enqueue(retried.run_id)
    return _run_response(retried)


@v1_router.post("/{run_id}/resume", response_model=EvaluationRunResponse)
def resume_evaluation_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    repo = evaluation_repository(session)
    run = repo.get_owned(run_id, user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    if run.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Evaluation is already active")
    if run.status == TaskStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Completed evaluations do not need to be resumed")
    resumed = repo.set_status(run_id, TaskStatus.QUEUED)
    from ..queue import LocalTaskQueue

    LocalTaskQueue(repo).enqueue(resumed.run_id)
    return _run_response(resumed)


@v1_router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evaluation_v1(
    run_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> None:
    repo = evaluation_repository(session)
    run = repo.get_owned(run_id, user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    if run.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Cancel the running evaluation before deleting it")
    if not repo.delete(run_id):
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    artifact_dir = settings.artifact_dir / run_id
    if artifact_dir.exists():
        import shutil

        shutil.rmtree(artifact_dir)
