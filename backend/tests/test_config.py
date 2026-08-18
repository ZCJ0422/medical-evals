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
