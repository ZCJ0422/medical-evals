from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_path: Path = Path("backend/data/medical-evals.sqlite3")
    artifact_dir: Path = Path("backend/data/artifacts")
    fixed_admin_username: str = "admin"
    fixed_admin_password_hash: str = ""
    token_secret: str = "development-only-medical-evals-token-secret"
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_prefix="MEDICAL_EVALS_", env_file=".env", extra="ignore")


settings = Settings()
