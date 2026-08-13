from fastapi import APIRouter, HTTPException, status

from ..auth import AdminIdentity, create_access_token, verify_password
from ..config import settings
from ..schemas.auth import AdminUser, LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    if payload.username != settings.fixed_admin_username or not verify_password(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return LoginResponse(access_token=create_access_token(payload.username), user=AdminUser(username=payload.username))
