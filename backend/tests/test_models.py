"""Tests for model structure and basic ORM behaviour.

These run against in-memory SQLite so no PostgreSQL instance is required.
"""

from collections.abc import Iterator
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Numeric, UniqueConstraint, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base
from app.models import (
    ImportBatch,
    ImportBatchStatus,
    ImportSourceType,
    Order,
    OrderStatus,
    RawImportedRecord,
    ReconciliationResult,
    ReconciliationStatus,
    Role,
    SettlementRecord,
    SettlementTransactionType,
    UploadedFile,
    User,
)

EXPECTED_TABLES = {
    "roles",
    "users",
    "orders",
    "uploaded_files",
    "import_batches",
    "raw_imported_records",
    "settlement_records",
    "reconciliation_results",
}

TABLES_WITH_UPDATED_AT = EXPECTED_TABLES - {"raw_imported_records"}


@pytest.fixture
def engine() -> Iterator[Engine]:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as db_session:
        yield db_session


def _foreign_key(table_name: str, column_name: str):
    column = Base.metadata.tables[table_name].columns[column_name]
    assert len(column.foreign_keys) == 1, f"{table_name}.{column_name} should have one FK"
    return next(iter(column.foreign_keys))


# --- Structural tests ------------------------------------------------------


def test_all_expected_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_table_has_an_integer_primary_key() -> None:
    for name, table in Base.metadata.tables.items():
        primary_key = list(table.primary_key.columns)
        assert primary_key, f"{name} has no primary key"
        assert [column.name for column in primary_key] == ["id"]


def test_monetary_columns_use_numeric_14_2() -> None:
    checked = 0
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.name.endswith("_amount"):
                assert isinstance(column.type, Numeric), f"{table.name}.{column.name}"
                assert (column.type.precision, column.type.scale) == (14, 2)
                checked += 1
    # orders(5) + settlement_records(4) + reconciliation_results(3)
    assert checked == 12


def test_timestamp_columns_are_present() -> None:
    for name in TABLES_WITH_UPDATED_AT:
        columns = Base.metadata.tables[name].columns
        assert "created_at" in columns, name
        assert "updated_at" in columns, name

    # Raw rows are immutable, so only created_at is tracked.
    raw_columns = Base.metadata.tables["raw_imported_records"].columns
    assert "created_at" in raw_columns
    assert "updated_at" not in raw_columns


def test_timestamp_columns_are_not_nullable_and_have_server_defaults() -> None:
    for name in TABLES_WITH_UPDATED_AT:
        for column_name in ("created_at", "updated_at"):
            column = Base.metadata.tables[name].columns[column_name]
            assert column.nullable is False
            assert column.server_default is not None


def test_business_key_unique_constraints() -> None:
    def unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
        table = Base.metadata.tables[table_name]
        return {
            tuple(sorted(column.name for column in constraint.columns))
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }

    assert ("external_order_id", "marketplace") in unique_column_sets("orders")
    assert ("external_reference", "marketplace") in unique_column_sets("settlement_records")


def test_foreign_keys_target_the_right_tables_and_delete_rules() -> None:
    assert _foreign_key("users", "role_id").target_fullname == "roles.id"
    assert _foreign_key("users", "role_id").ondelete == "RESTRICT"

    assert _foreign_key("import_batches", "uploaded_file_id").target_fullname == "uploaded_files.id"
    assert _foreign_key("import_batches", "uploaded_file_id").ondelete == "CASCADE"

    assert (
        _foreign_key("raw_imported_records", "import_batch_id").target_fullname
        == "import_batches.id"
    )
    assert _foreign_key("raw_imported_records", "import_batch_id").ondelete == "CASCADE"

    assert _foreign_key("settlement_records", "order_id").target_fullname == "orders.id"
    assert _foreign_key("settlement_records", "order_id").ondelete == "SET NULL"

    assert (
        _foreign_key("reconciliation_results", "order_id").target_fullname == "orders.id"
    )
    assert _foreign_key("reconciliation_results", "order_id").ondelete == "CASCADE"


def test_expected_indexes_are_declared() -> None:
    def index_names(table_name: str) -> set[str]:
        return {index.name for index in Base.metadata.tables[table_name].indexes}

    assert "ix_orders_marketplace_order_date" in index_names("orders")
    assert "ix_import_batches_source_status" in index_names("import_batches")
    assert "ix_settlement_records_marketplace_settlement_date" in index_names("settlement_records")
    assert "ix_raw_imported_records_batch_row" in index_names("raw_imported_records")


def test_enum_columns_store_lowercase_values_with_check_constraints() -> None:
    status_column = Base.metadata.tables["orders"].columns["status"]

    assert status_column.type.native_enum is False
    assert status_column.type.create_constraint is True
    assert set(status_column.type.enums) == {member.value for member in OrderStatus}
    assert status_column.server_default.arg == OrderStatus.PENDING.value


# --- Behavioural tests -----------------------------------------------------


def _build_graph(session: Session) -> tuple[Order, SettlementRecord, ReconciliationResult, User]:
    role = Role(name="finance_executive", description="Handles reconciliation")
    user = User(
        email="finance@example.com",
        full_name="Finance Executive",
        password_hash="test-password-hash",
        role=role,
    )

    order = Order(
        external_order_id="AMZ-1001",
        marketplace="amazon",
        order_date=datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
        status=OrderStatus.DELIVERED,
        gross_amount=Decimal("100.00"),
        net_amount=Decimal("90.00"),
    )

    uploaded_file = UploadedFile(
        original_filename="settlements_jan.csv",
        content_type="text/csv",
        size_bytes=2048,
        uploaded_by=user,
    )
    batch = ImportBatch(
        uploaded_file=uploaded_file,
        source_type=ImportSourceType.SETTLEMENTS,
        status=ImportBatchStatus.COMPLETED,
        marketplace="amazon",
        total_rows=1,
        processed_rows=1,
        created_by=user,
    )
    raw_record = RawImportedRecord(
        import_batch=batch,
        row_number=1,
        raw_data={"order_id": "AMZ-1001", "amount": "90.00"},
    )
    settlement = SettlementRecord(
        marketplace="amazon",
        external_reference="STL-9001",
        transaction_type=SettlementTransactionType.SALE,
        settlement_date=datetime(2026, 1, 20, 6, 0, tzinfo=timezone.utc),
        gross_amount=Decimal("100.00"),
        fee_amount=Decimal("10.00"),
        net_amount=Decimal("90.00"),
        order=order,
        import_batch=batch,
        raw_record=raw_record,
    )
    result = ReconciliationResult(
        order=order,
        settlement_record=settlement,
        import_batch=batch,
        status=ReconciliationStatus.MATCHED,
        expected_amount=Decimal("90.00"),
        actual_amount=Decimal("90.00"),
        difference_amount=Decimal("0.00"),
    )

    session.add_all([role, user, order, uploaded_file, batch, raw_record, settlement, result])
    session.commit()
    return order, settlement, result, user


def test_orm_round_trip_persists_and_links_entities(session: Session) -> None:
    order, settlement, result, user = _build_graph(session)
    order_id = order.id

    session.expire_all()

    reloaded = session.get(Order, order_id)
    assert reloaded is not None
    assert reloaded.external_order_id == "AMZ-1001"
    assert reloaded.status is OrderStatus.DELIVERED
    assert reloaded.net_amount == Decimal("90.00")

    # Relationships resolve in both directions.
    assert [record.external_reference for record in reloaded.settlement_records] == ["STL-9001"]
    assert reloaded.settlement_records[0].order.id == order_id
    assert [item.status for item in reloaded.reconciliation_results] == [
        ReconciliationStatus.MATCHED
    ]

    assert settlement.raw_record.raw_data == {"order_id": "AMZ-1001", "amount": "90.00"}
    assert result.import_batch.uploaded_file.original_filename == "settlements_jan.csv"
    assert user.role.name == "finance_executive"


def test_server_defaults_are_applied_on_insert(session: Session) -> None:
    role = Role(name="co_founder")
    user = User(
        email="founder@example.com",
        full_name="Co Founder",
        password_hash="test-password-hash",
        role=role,
    )
    session.add(user)
    session.commit()

    session.refresh(user)
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None


def test_relationship_cascade_deletes_reconciliation_results(session: Session) -> None:
    order, _settlement, _result, _user = _build_graph(session)

    session.delete(order)
    session.commit()

    remaining = session.scalar(select(func.count()).select_from(ReconciliationResult))
    assert remaining == 0


def test_raw_records_are_removed_with_their_import_batch(session: Session) -> None:
    _order, _settlement, _result, _user = _build_graph(session)

    batch = session.scalar(select(ImportBatch))
    assert batch is not None

    session.delete(batch)
    session.commit()

    assert session.scalar(select(func.count()).select_from(RawImportedRecord)) == 0
