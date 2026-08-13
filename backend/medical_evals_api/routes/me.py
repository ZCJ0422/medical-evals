from fastapi import APIRouter, Depends

from ..auth import AdminIdentity, require_admin
from ..schemas.auth import AdminUser

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/me", response_model=AdminUser)
def me(identity: AdminIdentity = Depends(require_admin)) -> AdminUser:
    return AdminUser(username=identity.username, role=identity.role)
