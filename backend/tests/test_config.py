import pytest

from medical_evals_api.config import Settings, validate_runtime_security


def test_production_rejects_development_credentials_and_secrets() -> None:
    settings = Settings(
        environment="production",
        fixed_admin_password_hash="",
        token_secret="development-only-medical-evals-token-secret",
        encryption_secret="development-only-medical-evals-encryption-secret",
    )

    with pytest.raises(RuntimeError, match="production configuration"):
        validate_runtime_security(settings)


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
