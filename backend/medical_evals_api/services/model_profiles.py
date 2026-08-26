from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.model_profiles import ModelProfile
from ..openai_compatible import OpenAICompatibleClient
from ..repositories.model_profiles import ModelProfileRepository
from ..schemas.model_profiles import ModelProfileCreate, ModelProfilePublic, ModelProfileUpdate
from ..secrets import decrypt_secret, encrypt_secret


class ModelProfileValidationError(ValueError):
    pass


class ModelProfileNotFoundError(LookupError):
    pass


class ModelProfileConnectionTestError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class ModelCredentials:
    base_url: str
    model_name: str
    api_key: str


def _normalize_non_empty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ModelProfileValidationError(f"{field_name} is required")
    return normalized


def _normalize_base_url(value: str) -> str:
    normalized = _normalize_non_empty(value, field_name="Base URL").rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ModelProfileValidationError("Base URL must be a complete http:// or https:// URL")
    if parsed.username is not None or parsed.password is not None:
        raise ModelProfileValidationError("Base URL must not include embedded credentials")
    return normalized


def _as_public(profile: ModelProfile) -> ModelProfilePublic:
    return ModelProfilePublic(
        id=profile.id,
        name=profile.name,
        base_url=profile.base_url,
        model_name=profile.model_name,
        has_api_key=bool(profile.api_key_encrypted),
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


class ModelProfileService:
    def __init__(self, session: Session):
        self.repository = ModelProfileRepository(session)

    def list_for_user(self, user_id: str) -> list[ModelProfilePublic]:
        return [_as_public(profile) for profile in self.repository.list_for_user(user_id)]

    def get(self, profile_id: str, user_id: str) -> ModelProfilePublic:
        profile = self.repository.get_for_user(profile_id, user_id)
        if profile is None:
            raise ModelProfileNotFoundError("Model profile not found")
        return _as_public(profile)

    def create(self, user_id: str, payload: ModelProfileCreate) -> ModelProfilePublic:
        try:
            profile = self.repository.create(
                user_id=user_id,
                name=_normalize_non_empty(payload.name, field_name="Name"),
                base_url=_normalize_base_url(payload.base_url),
                model_name=_normalize_non_empty(payload.model_name, field_name="Model name"),
                api_key_encrypted=encrypt_secret(_normalize_non_empty(payload.api_key, field_name="API key")),
            )
        except IntegrityError as exc:
            raise ModelProfileValidationError("Model profile name already exists") from exc
        return _as_public(profile)

    def update(self, profile_id: str, user_id: str, payload: ModelProfileUpdate) -> ModelProfilePublic:
        existing = self.repository.get_for_user(profile_id, user_id)
        if existing is None:
            raise ModelProfileNotFoundError("Model profile not found")
        try:
            updated = self.repository.update_for_user(
                profile_id,
                user_id,
                name=_normalize_non_empty(payload.name, field_name="Name") if payload.name is not None else None,
                base_url=_normalize_base_url(payload.base_url) if payload.base_url is not None else None,
                model_name=_normalize_non_empty(payload.model_name, field_name="Model name") if payload.model_name is not None else None,
                api_key_encrypted=encrypt_secret(_normalize_non_empty(payload.api_key, field_name="API key")) if payload.api_key is not None else None,
            )
        except IntegrityError as exc:
            raise ModelProfileValidationError("Model profile name already exists") from exc
        assert updated is not None
        return _as_public(updated)

    def delete(self, profile_id: str, user_id: str) -> None:
        if not self.repository.delete_for_user(profile_id, user_id):
            raise ModelProfileNotFoundError("Model profile not found")

    def resolve_secret(self, profile_id: str, user_id: str) -> ModelCredentials:
        profile = self.repository.get_for_user(profile_id, user_id)
        if profile is None:
            raise ModelProfileNotFoundError("Model profile not found")
        return ModelCredentials(
            base_url=profile.base_url,
            model_name=profile.model_name,
            api_key=decrypt_secret(profile.api_key_encrypted),
        )

    def test_connection(self, profile_id: str, user_id: str) -> None:
        credentials = self.resolve_secret(profile_id, user_id)
        client = OpenAICompatibleClient(
            credentials.base_url,
            credentials.api_key,
            timeout=10.0,
            max_retries=0,
        )
        try:
            client.complete(
                "ping",
                model=credentials.model_name,
                temperature=0,
                max_tokens=1,
            )
        except httpx.TimeoutException as exc:
            raise ModelProfileConnectionTestError(
                "Model provider timed out during the connection test",
                status_code=504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ModelProfileConnectionTestError(
                "Model provider rejected the connection test",
                status_code=502,
            ) from exc
        except httpx.RequestError as exc:
            raise ModelProfileConnectionTestError(
                "Model provider could not be reached",
                status_code=502,
            ) from exc
        finally:
            client.close()
