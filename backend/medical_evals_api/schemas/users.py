from pydantic import BaseModel, Field


class UserCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=1024)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class UserResponse(BaseModel):
    username: str
    role: str
    status: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
