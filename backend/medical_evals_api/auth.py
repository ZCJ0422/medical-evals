import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from .config import settings


@dataclass(frozen=True)
class AdminIdentity:
    username: str
    role: str = "admin"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _password_digest(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str) -> bool:
    configured = settings.fixed_admin_password_hash
    expected = configured or _password_digest("medical-evals-admin")
    return hmac.compare_digest(_password_digest(password), expected)


def create_access_token(username: str, ttl_seconds: int = 3600) -> str:
    payload = {"sub": username, "role": "admin", "exp": int(time.time()) + ttl_seconds}
    encoded = _b64(json.dumps(payload, separators=(",", ":")).encode())
    secret = settings.token_secret.encode()
    signature = _b64(hmac.new(secret, encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def decode_access_token(token: str) -> AdminIdentity:
    try:
        encoded, signature = token.split(".", 1)
        expected = _b64(hmac.new(settings.token_secret.encode(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        payload = json.loads(_unb64(encoded))
        if payload.get("role") != "admin" or int(payload["exp"]) <= int(time.time()):
            raise ValueError("expired token")
        return AdminIdentity(username=str(payload["sub"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token") from exc


def require_admin(request: Request) -> AdminIdentity:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    identity = decode_access_token(token)
    if identity.username != settings.fixed_admin_username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return identity
