from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from typing import Annotated

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import settings
from .database import get_session
from .models.users import User
from .repositories.users import UserRepository


ACCESS_TOKEN_TTL_SECONDS = 900
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30

AdminIdentity = User


def _b64url_encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode().rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    kdf = Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=64 * 1024)
    return kdf.derive_phc_encoded(password.encode())


def verify_password(password: str, digest: str) -> bool:
    try:
        Argon2id.verify_phc_encoded(password.encode(), digest)
        return True
    except InvalidKey:
        return False


def _hash_refresh_token(token: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def create_access_token(
    username: str,
    ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS,
    *,
    user_id: str | None = None,
    role: str = "admin",
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "uid": user_id,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = _b64url_encode(hmac.new(settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256).digest())
    return f"{signing_input}.{signature}"


def _decode_access_token(token: str) -> dict[str, str | None]:
    try:
        encoded_header, encoded_payload, signature = token.split(".")
        signing_input = f"{encoded_header}.{encoded_payload}"
        expected_signature = _b64url_encode(hmac.new(settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("invalid signature")
        header = json.loads(_b64url_decode(encoded_header))
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise ValueError("invalid header")
        payload = json.loads(_b64url_decode(encoded_payload))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
    username = payload.get("sub")
    role = payload.get("role")
    user_id = payload.get("uid")
    if not isinstance(username, str) or not username or not isinstance(role, str) or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
    if user_id is not None and not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
    return {"username": username, "role": role, "user_id": user_id}


def issue_token_pair(user: User, repository: UserRepository) -> tuple[str, str]:
    access_token = create_access_token(user.username, user_id=user.id, role=user.role)
    refresh_token = secrets.token_urlsafe(32)
    repository.create_refresh_token(
        user_id=user.id,
        token_hash=_hash_refresh_token(refresh_token),
        expires_in_seconds=REFRESH_TOKEN_TTL_SECONDS,
    )
    return access_token, refresh_token


def require_user(request: Request, session: Session = Depends(get_session)) -> User:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    claims = _decode_access_token(token)
    repository = UserRepository(session)
    user = repository.get_by_id(claims["user_id"]) if claims["user_id"] else repository.get_by_username(claims["username"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    return user


def require_admin(request: Request, session: Session = Depends(get_session)) -> User:
    user = require_user(request, session)
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user


CurrentUser = Annotated[User, Depends(require_user)]
