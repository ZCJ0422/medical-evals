from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import project_root


class Settings(BaseSettings):
    environment: str = "development"
    database_path: Path = project_root() / "backend/data/medical-evals.sqlite3"
    artifact_dir: Path = project_root() / "backend/data/artifacts"
    fixed_admin_username: str = "admin"
    fixed_admin_password_hash: str = ""
    token_secret: str = "development-only-medical-evals-token-secret"
    encryption_secret: str = "development-only-medical-evals-encryption-secret"
    frontend_origin: str = "http://localhost:3000"
    worker_lease_seconds: int = Field(default=300, ge=30, le=86400)

    model_config = SettingsConfigDict(env_prefix="MEDICAL_EVALS_", env_file=".env", extra="ignore")

    def model_post_init(self, __context) -> None:
        # Resolve relative env overrides from the repository root, not from
        # whichever directory happened to launch API and Worker.
        for field_name in ("database_path", "artifact_dir"):
            value = getattr(self, field_name)
            if not value.is_absolute():
                setattr(self, field_name, project_root() / value)


settings = Settings()


def validate_runtime_security(runtime_settings: Settings = settings) -> None:
    """Fail closed for production, while preserving the documented local setup."""
    if runtime_settings.environment.lower() not in {"production", "prod"}:
        return
    unsafe = []
    if not runtime_settings.fixed_admin_password_hash:
        unsafe.append("MEDICAL_EVALS_FIXED_ADMIN_PASSWORD_HASH")
    if runtime_settings.token_secret == "development-only-medical-evals-token-secret":
        unsafe.append("MEDICAL_EVALS_TOKEN_SECRET")
    if runtime_settings.encryption_secret == "development-only-medical-evals-encryption-secret":
        unsafe.append("MEDICAL_EVALS_ENCRYPTION_SECRET")
    if unsafe:
        raise RuntimeError(f"Unsafe production configuration; set: {', '.join(unsafe)}")
