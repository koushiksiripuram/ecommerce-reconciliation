"""Tests for environment-driven configuration."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_database_url_is_built_from_discrete_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_USER", "recon")
    monkeypatch.setenv("POSTGRES_PASSWORD", "s3cret")
    monkeypatch.setenv("POSTGRES_DB", "recon_db")

    settings = Settings(_env_file=None)

    assert settings.database_url == (
        "postgresql+psycopg2://recon:s3cret@db.internal:6543/recon_db"
    )


def test_database_url_override_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "ignored-host")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@hosted.example.com:5432/app")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg2://u:p@hosted.example.com:5432/app"


def test_defaults_are_safe_and_local() -> None:
    settings = Settings(_env_file=None)

    assert settings.api_prefix == "/api"
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.database_url.startswith("postgresql+psycopg2://")


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_no_credentials_are_hardcoded_in_source() -> None:
    """Placeholder defaults must be obviously non-production values."""
    settings = Settings(_env_file=None)

    assert settings.database_url_override is None
    assert settings.postgres_password == "postgres"


def test_cors_origins_parses_json_array(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["https://app.example.com","http://localhost:3000"]')

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["https://app.example.com", "http://localhost:3000"]


def test_auth_defaults_are_present() -> None:
    settings = Settings(_env_file=None)

    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_token_expire_minutes == 60
    assert settings.auth_cookie_name == "access_token"
    assert settings.auth_cookie_secure is False
    assert settings.auth_cookie_samesite == "lax"


def test_jwt_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "env-provided-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS512")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_COOKIE_SAMESITE", "none")

    settings = Settings(_env_file=None)

    assert settings.jwt_secret_key == "env-provided-secret"
    assert settings.jwt_algorithm == "HS512"
    assert settings.jwt_access_token_expire_minutes == 15
    assert settings.auth_cookie_secure is True
    assert settings.auth_cookie_samesite == "none"


def test_placeholder_jwt_secret_is_rejected_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_real_jwt_secret_is_accepted_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-long-random-production-secret")

    settings = Settings(_env_file=None)

    assert settings.jwt_secret_key == "a-long-random-production-secret"
