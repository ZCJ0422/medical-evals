import pytest
from fastapi.testclient import TestClient

from medical_evals_api import config
from medical_evals_api.config import Settings, validate_runtime_security
from medical_evals_api.main import app


@pytest.mark.parametrize(
    "jwt_secret",
    [
        "development-only-medical-evals-token-secret",
        "development-only-medical-evals-jwt-secret",
    ],
)
def test_production_rejects_legacy_and_new_development_jwt_secrets(jwt_secret: str) -> None:
    settings = Settings(
        environment="production",
        fixed_admin_password_hash="safe-password-hash",
        jwt_secret=jwt_secret,
        encryption_secret="safe-encryption-secret",
    )

    with pytest.raises(RuntimeError, match="MEDICAL_EVALS_JWT_SECRET"):
        validate_runtime_security(settings)


def test_production_accepts_non_default_jwt_secret() -> None:
    settings = Settings(
        environment="production",
        fixed_admin_password_hash="safe-password-hash",
        jwt_secret="safe-jwt-secret",
        encryption_secret="safe-encryption-secret",
    )

    validate_runtime_security(settings)
    assert settings.jwt_secret == "safe-jwt-secret"


def test_development_keeps_local_defaults_usable() -> None:
    validate_runtime_security(Settings(environment="development"))


def test_storage_paths_are_rooted_at_the_repository() -> None:
    settings = Settings(
        database_path="backend/data/custom.sqlite3",
        artifact_dir="backend/data/custom-artifacts",
    )

    assert settings.database_path.is_absolute()
    assert settings.artifact_dir.is_absolute()
    assert settings.database_path.parts[-3:] == ("backend", "data", "custom.sqlite3")
    assert settings.artifact_dir.parts[-3:] == ("backend", "data", "custom-artifacts")


def test_worker_lease_duration_is_configurable_with_safe_bounds() -> None:
    assert Settings(worker_lease_seconds=600).worker_lease_seconds == 600
    with pytest.raises(ValueError):
        Settings(worker_lease_seconds=29)
    with pytest.raises(ValueError):
        Settings(worker_lease_seconds=86401)


def test_api_startup_rejects_unsafe_production_defaults(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "environment", "production")
    monkeypatch.setattr(config.settings, "fixed_admin_password_hash", "")
    monkeypatch.setattr(config.settings, "token_secret", "development-only-medical-evals-token-secret")
    monkeypatch.setattr(config.settings, "encryption_secret", "development-only-medical-evals-encryption-secret")

    with pytest.raises(RuntimeError, match="production configuration"), TestClient(app):
        pass
