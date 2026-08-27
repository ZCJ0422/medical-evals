from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Annotated
from urllib.parse import urlsplit

import redis
from fastapi import Depends, HTTPException, Request, status
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from .config import settings
from .database import get_redis

_HTTP_URL = TypeAdapter(AnyHttpUrl)
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata"}
_BLOCKED_IPS = {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("100.100.100.200")}


def _blocked_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return address.is_loopback or address.is_private or address.is_link_local or address.is_reserved or address in _BLOCKED_IPS


def validate_public_base_url(url: str) -> AnyHttpUrl:
    try:
        parsed = _HTTP_URL.validate_python(url)
    except ValidationError as exc:
        raise ValueError("Base URL must be a complete http:// or https:// URL") from exc
    parts = urlsplit(str(parsed))
    host = (parts.hostname or "").rstrip(".").lower()
    if parts.username is not None or parts.password is not None:
        raise ValueError("Base URL must not include embedded credentials")
    if host in _BLOCKED_HOSTS:
        raise ValueError("Base URL must resolve to a public host")
    try:
        if _blocked_ip(host):
            raise ValueError("Base URL must resolve to a public host")
    except ValueError as exc:
        if str(exc) == "Base URL must resolve to a public host":
            raise
        # Hostnames are resolved when possible. Unresolvable test/provider
        # domains are left for the connection test to report safely.
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, parts.port, type=socket.SOCK_STREAM)}
        except socket.gaierror:
            addresses = set()
        if any(_blocked_ip(address) for address in addresses):
            raise ValueError("Base URL must resolve to a public host") from exc
    return parsed


def _client_key(request: Request, bucket: str) -> str:
    # Do not trust a client-supplied forwarding header unless a trusted proxy
    # has already rewritten the ASGI client address.
    source = request.client.host if request.client else "unknown"
    return f"medical-evals:rate:{bucket}:{source}"


def _rate_limit_redis() -> redis.Redis:
    return get_redis(settings)


def rate_limit(bucket: str, *, limit: int = 10, window_seconds: int = 60) -> Callable:
    def dependency(request: Request, redis_client: Annotated[redis.Redis, Depends(_rate_limit_redis)]) -> None:
        try:
            key = _client_key(request, bucket)
            count = int(redis_client.incr(key))
            if count == 1:
                redis_client.expire(key, window_seconds)
        except redis.exceptions.RedisError as exc:
            if settings.environment.lower() in {"production", "prod"}:
                raise HTTPException(status_code=503, detail="Rate limiting unavailable") from exc
            return
        if count > limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")

    return dependency
