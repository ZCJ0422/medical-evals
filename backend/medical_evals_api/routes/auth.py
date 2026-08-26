from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import CurrentUser, _hash_refresh_token, hash_password, issue_token_pair, verify_password
from ..database import get_session
from ..repositories.users import UserRepository
from ..schemas.users import RefreshTokenRequest, TokenResponse, UserCredentials, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
v1_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
me_router = APIRouter(prefix="/api", tags=["auth"])
v1_me_router = APIRouter(prefix="/api/v1", tags=["auth"])


def _tokens_for(user, repository: UserRepository) -> TokenResponse:
    access_token, refresh_token = issue_token_pair(user, repository)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(username=user.username, role=user.role, status=user.status),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _register(payload: UserCredentials, session: Session) -> TokenResponse:
    repository = UserRepository(session)
    try:
        user = repository.create_user(username=payload.username.strip(), password_hash=hash_password(payload.password))
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists") from exc
    return _tokens_for(user, repository)


def _login(payload: UserCredentials, session: Session) -> TokenResponse:
    repository = UserRepository(session)
    user = repository.get_by_username(payload.username.strip())
    if user is None or user.status != "active" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return _tokens_for(user, repository)


def _refresh(payload: RefreshTokenRequest, session: Session) -> TokenResponse:
    repository = UserRepository(session)
    token_hash = _hash_refresh_token(payload.refresh_token)
    record = repository.get_refresh_token(token_hash)
    if record is None or record.revoked_at is not None or _as_utc(record.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = repository.get_by_id(record.user_id)
    if user is None or user.status != "active":
        repository.revoke_refresh_token(token_hash)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    repository.revoke_refresh_token(token_hash)
    return _tokens_for(user, repository)


def _logout(payload: RefreshTokenRequest, session: Session) -> Response:
    UserRepository(session).revoke_refresh_token(_hash_refresh_token(payload.refresh_token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCredentials, session: Session = Depends(get_session)) -> TokenResponse:
    return _register(payload, session)


@v1_router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def register_v1(payload: UserCredentials, session: Session = Depends(get_session)) -> TokenResponse:
    return _register(payload, session)


@router.post("/login", response_model=TokenResponse)
def login(payload: UserCredentials, session: Session = Depends(get_session)) -> TokenResponse:
    return _login(payload, session)


@v1_router.post("/login", response_model=TokenResponse, include_in_schema=False)
def login_v1(payload: UserCredentials, session: Session = Depends(get_session)) -> TokenResponse:
    return _login(payload, session)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshTokenRequest, session: Session = Depends(get_session)) -> TokenResponse:
    return _refresh(payload, session)


@v1_router.post("/refresh", response_model=TokenResponse, include_in_schema=False)
def refresh_v1(payload: RefreshTokenRequest, session: Session = Depends(get_session)) -> TokenResponse:
    return _refresh(payload, session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshTokenRequest, session: Session = Depends(get_session)) -> Response:
    return _logout(payload, session)


@v1_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def logout_v1(payload: RefreshTokenRequest, session: Session = Depends(get_session)) -> Response:
    return _logout(payload, session)


def me(user: CurrentUser) -> UserResponse:
    return UserResponse(username=user.username, role=user.role, status=user.status)


me_router.add_api_route("/me", me, methods=["GET"], response_model=UserResponse)
v1_me_router.add_api_route("/me", me, methods=["GET"], response_model=UserResponse, include_in_schema=False)
