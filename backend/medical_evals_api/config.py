from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import project_root


class Settings(BaseSettings):
    environment: str = "development"
    database_path: Path = project_root() / "backend/data/medical-evals.sqlite3"
    database_url: str = Field(
        default="postgresql+psycopg://medical_evals:medical_evals@localhost:5432/medical_evals",
        validation_alias=AliasChoices("MEDICAL_EVALS_DATABASE_URL"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("MEDICAL_EVALS_REDIS_URL"),
    )
    artifact_dir: Path = project_root() / "backend/data/artifacts"
    fixed_admin_username: str = "admin"
    fixed_admin_password_hash: str = ""
    jwt_secret: str = Field(
        default="development-only-medical-evals-jwt-secret",
        validation_alias=AliasChoices("MEDICAL_EVALS_JWT_SECRET", "MEDICAL_EVALS_TOKEN_SECRET"),
    )
    encryption_secret: str = "development-only-medical-evals-encryption-secret"
    frontend_origin: str = "http://localhost:3000"
    worker_lease_seconds: int = Field(default=300, ge=30, le=86400)

    model_config = SettingsConfigDict(env_prefix="MEDICAL_EVALS_", env_file=".env", extra="ignore", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_token_secret(cls, value):
        if isinstance(value, dict) and "jwt_secret" not in value and "token_secret" in value:
            value = dict(value)
            value["jwt_secret"] = value["token_secret"]
        return value

    def model_post_init(self, __context) -> None:
        # Resolve relative env overrides from the repository root, not from
        # whichever directory happened to launch API and Worker.
        for field_name in ("database_path", "artifact_dir"):
            value = getattr(self, field_name)
            if not value.is_absolute():
                setattr(self, field_name, project_root() / value)

    @property
    def token_secret(self) -> str:
        return self.jwt_secret

    @token_secret.setter
    def token_secret(self, value: str) -> None:
        object.__setattr__(self, "jwt_secret", value)


settings = Settings()


def validate_runtime_security(runtime_settings: Settings = settings) -> None:
    """Fail closed for production, while preserving the documented local setup."""
    if runtime_settings.environment.lower() not in {"production", "prod"}:
        return
    unsafe_jwt_secrets = {
        "development-only-medical-evals-jwt-secret",
        "development-only-medical-evals-token-secret",
    }
    unsafe = []
    if not runtime_settings.fixed_admin_password_hash:
        unsafe.append("MEDICAL_EVALS_FIXED_ADMIN_PASSWORD_HASH")
    if runtime_settings.jwt_secret in unsafe_jwt_secrets:
        unsafe.append("MEDICAL_EVALS_JWT_SECRET")
    if runtime_settings.encryption_secret == "development-only-medical-evals-encryption-secret":
        unsafe.append("MEDICAL_EVALS_ENCRYPTION_SECRET")
    if unsafe:
        raise RuntimeError(f"Unsafe production configuration; set: {', '.join(unsafe)}")
