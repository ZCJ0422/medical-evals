from __future__ import annotations

from typing import Any

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import insert, select, update, delete
from sqlalchemy.orm import Session

from ..database import metadata, model_profiles
from ..models.model_profiles import ModelProfile


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _profile_from_row(row) -> ModelProfile:
    return ModelProfile(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        base_url=row.base_url,
        model_name=row.model_name,
        api_key_encrypted=row.api_key_encrypted,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ModelProfileRepository:
    def __init__(self, session: Session):
        self.session = session
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        metadata.create_all(self.session.bind, tables=[model_profiles], checkfirst=True)

    def create(
        self,
        *,
        user_id: str,
        name: str,
        base_url: str,
        model_name: str,
        api_key_encrypted: str,
    ) -> ModelProfile:
        profile_id = str(uuid4())
        now = _utcnow()
        self.session.execute(
            insert(model_profiles).values(
                id=profile_id,
                user_id=user_id,
                name=name,
                base_url=base_url,
                model_name=model_name,
                api_key_encrypted=api_key_encrypted,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        created = self.get_for_user(profile_id, user_id)
        assert created is not None
        return created

    def list_for_user(self, user_id: str) -> list[ModelProfile]:
        rows = self.session.execute(
            select(model_profiles)
            .where(model_profiles.c.user_id == user_id)
            .order_by(model_profiles.c.created_at.asc(), model_profiles.c.id.asc())
        ).mappings()
        return [_profile_from_row(row) for row in rows]

    def get_for_user(self, profile_id: str, user_id: str) -> ModelProfile | None:
        row = self.session.execute(
            select(model_profiles).where(
                model_profiles.c.id == profile_id,
                model_profiles.c.user_id == user_id,
            )
        ).mappings().first()
        return _profile_from_row(row) if row is not None else None

    def update_for_user(
        self,
        profile_id: str,
        user_id: str,
        *,
        name: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key_encrypted: str | None = None,
    ) -> ModelProfile | None:
        values: dict[str, Any] = {"updated_at": _utcnow()}
        if name is not None:
            values["name"] = name
        if base_url is not None:
            values["base_url"] = base_url
        if model_name is not None:
            values["model_name"] = model_name
        if api_key_encrypted is not None:
            values["api_key_encrypted"] = api_key_encrypted
        self.session.execute(
            update(model_profiles)
            .where(model_profiles.c.id == profile_id, model_profiles.c.user_id == user_id)
            .values(**values)
        )
        self.session.commit()
        return self.get_for_user(profile_id, user_id)

    def delete_for_user(self, profile_id: str, user_id: str) -> bool:
        result = self.session.execute(
            delete(model_profiles).where(
                model_profiles.c.id == profile_id,
                model_profiles.c.user_id == user_id,
            )
        )
        self.session.commit()
        return bool(result.rowcount)
