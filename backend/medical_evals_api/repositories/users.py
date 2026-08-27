from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import metadata, refresh_tokens, users
from ..models.users import RefreshTokenRecord, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_from_row(row) -> User:
    return User(
        id=row.id,
        username=row.username,
        password_hash=row.password_hash,
        role=row.role,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _refresh_from_row(row) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


class UserRepository:
    def __init__(self, session: Session):
        self.session = session
        self._ensure_tables()
        self.ensure_default_admin()

    def _ensure_tables(self) -> None:
        metadata.create_all(self.session.bind, tables=[users, refresh_tokens], checkfirst=True)

    def ensure_default_admin(self) -> User:
        existing = self.get_by_username(settings.fixed_admin_username)
        if existing is not None:
            return existing
        from ..auth import hash_password

        password_hash = settings.fixed_admin_password_hash or hash_password("medical-evals-admin")
        return self.create_user(
            username=settings.fixed_admin_username,
            password_hash=password_hash,
            role="admin",
            status="active",
        )

    def create_user(self, *, username: str, password_hash: str, role: str = "user", status: str = "active") -> User:
        user_id = str(uuid4())
        now = _utcnow()
        self.session.execute(
            insert(users).values(
                id=user_id,
                username=username,
                password_hash=password_hash,
                role=role,
                status=status,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        created = self.get_by_id(user_id)
        assert created is not None
        return created

    def get_by_username(self, username: str) -> User | None:
        row = self.session.execute(select(users).where(users.c.username == username)).mappings().first()
        return _user_from_row(row) if row is not None else None

    def get_by_id(self, user_id: str) -> User | None:
        row = self.session.execute(select(users).where(users.c.id == user_id)).mappings().first()
        return _user_from_row(row) if row is not None else None

    def set_status(self, user_id: str, status: str) -> User:
        now = _utcnow()
        self.session.execute(update(users).where(users.c.id == user_id).values(status=status, updated_at=now))
        self.session.commit()
        updated = self.get_by_id(user_id)
        assert updated is not None
        return updated

    def create_refresh_token(self, *, user_id: str, token_hash: str, expires_in_seconds: int) -> RefreshTokenRecord:
        record_id = str(uuid4())
        now = _utcnow()
        expires_at = now + timedelta(seconds=expires_in_seconds)
        self.session.execute(
            insert(refresh_tokens).values(
                id=record_id,
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
                revoked_at=None,
                created_at=now,
            )
        )
        self.session.commit()
        record = self.get_refresh_token(token_hash)
        assert record is not None
        return record

    def get_refresh_token(self, token_hash: str) -> RefreshTokenRecord | None:
        row = self.session.execute(select(refresh_tokens).where(refresh_tokens.c.token_hash == token_hash)).mappings().first()
        return _refresh_from_row(row) if row is not None else None

    def revoke_refresh_token(self, token_hash: str) -> None:
        self.session.execute(
            update(refresh_tokens)
            .where(refresh_tokens.c.token_hash == token_hash, refresh_tokens.c.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        self.session.commit()
