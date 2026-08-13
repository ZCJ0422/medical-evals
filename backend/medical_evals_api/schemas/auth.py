from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class AdminUser(BaseModel):
    username: str
    role: str = "admin"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AdminUser
