"""Tests that the Alembic migration is runnable and matches the models.

The migration is applied to a throwaway SQLite database, so these tests need
neither PostgreSQL nor network access.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base


def _alembic_config() -> Config:
    return Config("alembic.ini")


@pytest.fixture
def database_url(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Point the settings at a temp SQLite file and migrate it to head."""
    url = f"sqlite:///{(tmp_path / 'migration_test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    command.upgrade(_alembic_config(), "head")

    yield url

    get_settings.cache_clear()


@pytest.fixture
def migrated_engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


def test_upgrade_creates_every_model_table(migrated_engine: Engine) -> None:
    applied = set(inspect(migrated_engine).get_table_names())
    applied.discard("alembic_version")

    assert applied == set(Base.metadata.tables)


def test_revision_is_recorded_as_head(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        heads = connection.execute(
            text("SELECT COUNT(*) FROM alembic_version")
        ).scalar()

    assert version is not None
    assert heads == 1


def test_migration_matches_model_metadata(migrated_engine: Engine) -> None:
    """Migrating to head must reproduce exactly what the models declare."""
    with migrated_engine.connect() as connection:
        migration_context = MigrationContext.configure(connection)
        differences = compare_metadata(migration_context, Base.metadata)

    assert differences == []


def test_roles_are_seeded(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        names = connection.execute(text("SELECT name FROM roles ORDER BY name")).scalars().all()

    assert names == ["co_founder", "finance_executive"]


def test_migrated_schema_enforces_the_order_status_check_constraint(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.connect() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO orders (external_order_id, marketplace, order_date, status) "
                    "VALUES ('X-1', 'amazon', '2026-01-01 00:00:00', 'not_a_status')"
                )
            )


def test_downgrade_removes_every_table(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite:///{(tmp_path / 'downgrade_test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(url)
    try:
        remaining = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
        get_settings.cache_clear()

    assert remaining <= {"alembic_version"}
