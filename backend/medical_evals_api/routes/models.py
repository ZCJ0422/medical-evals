from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..auth import CurrentUser
from ..database import get_session
from ..schemas.model_profiles import (
    ModelConnectionTestResult,
    ModelProfileCreate,
    ModelProfilePublic,
    ModelProfileUpdate,
)
from ..security import rate_limit
from ..services.model_profiles import (
    ModelProfileConnectionTestError,
    ModelProfileNotFoundError,
    ModelProfileService,
    ModelProfileValidationError,
)

router = APIRouter(prefix="/api/v1/models", tags=["models"])


def _service(session: Session) -> ModelProfileService:
    return ModelProfileService(session)


@router.get("", response_model=list[ModelProfilePublic])
def list_model_profiles(
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> list[ModelProfilePublic]:
    return _service(session).list_for_user(user.id)


@router.post("", response_model=ModelProfilePublic, status_code=status.HTTP_201_CREATED)
def create_model_profile(
    payload: ModelProfileCreate,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> ModelProfilePublic:
    try:
        return _service(session).create(user.id, payload)
    except ModelProfileValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{profile_id}", response_model=ModelProfilePublic)
def get_model_profile(
    profile_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> ModelProfilePublic:
    try:
        return _service(session).get(profile_id, user.id)
    except ModelProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{profile_id}", response_model=ModelProfilePublic)
def update_model_profile(
    profile_id: str,
    payload: ModelProfileUpdate,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> ModelProfilePublic:
    try:
        return _service(session).update(profile_id, user.id, payload)
    except ModelProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelProfileValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_profile(
    profile_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> Response:
    try:
        _service(session).delete(profile_id, user.id)
    except ModelProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{profile_id}/test", response_model=ModelConnectionTestResult, dependencies=[Depends(rate_limit("model-test"))])
def test_model_profile(
    profile_id: str,
    user: CurrentUser,
    session: Session = Depends(get_session),
) -> ModelConnectionTestResult:
    try:
        _service(session).test_connection(profile_id, user.id)
    except ModelProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelProfileConnectionTestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return ModelConnectionTestResult(ok=True)
