"""Shared test fixtures."""

from collections.abc import Iterator

import pytest

from app.core.config import get_settings

# Variables that influence Settings and must not leak in from the host machine.
SETTINGS_ENV_VARS = (
    "DATABASE_URL",
    "APP_NAME",
    "ENVIRONMENT",
    "DEBUG",
    "API_PREFIX",
    "CORS_ORIGINS",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
)


@pytest.fixture(autouse=True)
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate settings from ambient environment variables and the cache."""
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
