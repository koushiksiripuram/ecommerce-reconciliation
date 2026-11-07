"""Shared test fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base

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
    "JWT_SECRET_KEY",
    "JWT_ALGORITHM",
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    "AUTH_COOKIE_NAME",
    "AUTH_COOKIE_SECURE",
    "AUTH_COOKIE_SAMESITE",
    "UPLOAD_STORAGE_DIR",
    "MAX_UPLOAD_SIZE_BYTES",
    "IMPORT_PREVIEW_ROWS",
    "IMPORT_BATCH_SIZE",
)


@pytest.fixture(autouse=True)
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate settings from ambient environment variables and the cache."""
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- Database --------------------------------------------------------------


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    """An in-memory SQLite database with every table created.

    ``StaticPool`` keeps every connection on the same in-memory database and
    ``check_same_thread=False`` lets FastAPI's worker thread reuse it, so the
    same fixture works for direct service calls and for ``TestClient``.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(sqlite_engine: Engine) -> sessionmaker[Session]:
    """A sessionmaker bound to the shared in-memory database."""
    return sessionmaker(bind=sqlite_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A ready-to-use session for tests that call the service directly."""
    with session_factory() as session:
        yield session


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point upload storage at a throwaway directory for the current test."""
    directory = tmp_path / "uploads"
    monkeypatch.setenv("UPLOAD_STORAGE_DIR", str(directory))
    get_settings.cache_clear()
    return directory
