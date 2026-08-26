from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    id: str
    username: str
    password_hash: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RefreshTokenRecord:
    id: str
    user_id: str
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
