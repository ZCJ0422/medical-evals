from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    database_path: Path = Path("backend/data/medical-evals.sqlite3")
    artifact_dir: Path = Path("backend/data/artifacts")
    fixed_admin_username: str = "admin"
    fixed_admin_password_hash: str = ""
    token_secret: str = "development-only-medical-evals-token-secret"
    encryption_secret: str = "development-only-medical-evals-encryption-secret"
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_prefix="MEDICAL_EVALS_", env_file=".env", extra="ignore")


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
