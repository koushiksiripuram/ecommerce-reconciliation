"""Tests for the import orchestration service.

These exercise the full batch lifecycle against in-memory SQLite and a
throwaway upload directory.
"""

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.imports import service
from app.imports.errors import (
    BatchNotFoundError,
    BatchStateError,
    DuplicateImportError,
    EmptyFileError,
    FileTooLargeError,
    InvalidRequestError,
    MappingError,
    SourceTypeNotSupportedError,
    UnsupportedFileTypeError,
)
from app.models import (
    ImportBatch,
    ImportBatchStatus,
    ImportColumnMapping,
    ImportSourceType,
    RawImportedRecord,
)

ORDERS = ImportSourceType.ORDERS
SETTLEMENTS = ImportSourceType.SETTLEMENTS

READY_CSV = b"Order ID,Order Date,Order Amount\nA-1,2026-01-05,100.00\n"
MIXED_CSV = (
    b"Order ID,Order Date,Order Amount\n"
    b'A-1,2026-01-05,"1,234.56"\n'
    b"A-2,2026-01-06,N/A\n"
)
UNMAPPED_CSV = b"ColX,ColY,ColZ\n1,2,3\n"


def _upload(
    db: Session,
    *,
    content: bytes = READY_CSV,
    filename: str = "orders.csv",
    source_type: ImportSourceType = ORDERS,
    partner: str = "amazon",
) -> ImportBatch:
    return service.store_upload(
        db,
        filename=filename,
        content=content,
        content_type="text/csv",
        source_type=source_type,
        partner=partner,
        user_id=None,
    )


# --- store_upload ----------------------------------------------------------


def test_store_upload_registers_a_ready_batch(db_session: Session, upload_dir: Path) -> None:
    batch = _upload(db_session)

    assert batch.id is not None
    assert batch.status is ImportBatchStatus.UPLOADED
    assert batch.marketplace == "amazon"
    assert batch.total_rows == 1
    assert batch.column_mapping == {
        "external_order_id": "Order ID",
        "order_date": "Order Date",
        "order_amount": "Order Amount",
    }


def test_store_upload_writes_the_file_to_disk(db_session: Session, upload_dir: Path) -> None:
    batch = _upload(db_session)

    stored = batch.uploaded_file
    assert stored is not None
    path = Path(stored.storage_path or "")
    assert path.is_file()
    assert path.read_bytes() == READY_CSV
    assert path.is_relative_to(upload_dir)


def test_store_upload_records_the_checksum(db_session: Session, upload_dir: Path) -> None:
    import hashlib

    batch = _upload(db_session)

    stored = batch.uploaded_file
    assert stored is not None
    assert stored.checksum_sha256 == hashlib.sha256(READY_CSV).hexdigest()


def test_store_upload_requires_a_partner(db_session: Session, upload_dir: Path) -> None:
    with pytest.raises(InvalidRequestError):
        _upload(db_session, partner="   ")


def test_store_upload_rejects_an_unsupported_source_type(
    db_session: Session, upload_dir: Path
) -> None:
    with pytest.raises(SourceTypeNotSupportedError):
        _upload(db_session, source_type=ImportSourceType.CLAIMS)


def test_store_upload_rejects_an_unsupported_extension(
    db_session: Session, upload_dir: Path
) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        _upload(db_session, filename="statement.pdf")


def test_store_upload_rejects_an_empty_file(db_session: Session, upload_dir: Path) -> None:
    with pytest.raises(EmptyFileError):
        _upload(db_session, content=b"")


def test_store_upload_rejects_an_oversized_file(
    db_session: Session, upload_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", "10")
    get_settings.cache_clear()

    with pytest.raises(FileTooLargeError):
        _upload(db_session)


def test_store_upload_marks_mapping_required_when_fields_are_missing(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session, content=UNMAPPED_CSV)

    assert batch.status is ImportBatchStatus.MAPPING_REQUIRED
    assert batch.column_mapping is None


def test_store_upload_rejects_a_duplicate_file(db_session: Session, upload_dir: Path) -> None:
    first = _upload(db_session)

    with pytest.raises(DuplicateImportError) as excinfo:
        _upload(db_session)

    assert excinfo.value.existing_batch_id == first.id


def test_store_upload_treats_a_different_partner_as_a_new_batch(
    db_session: Session, upload_dir: Path
) -> None:
    first = _upload(db_session, partner="amazon")
    second = _upload(db_session, partner="flipkart")

    assert first.id != second.id


def test_store_upload_allows_retry_after_a_failed_batch(
    db_session: Session, upload_dir: Path
) -> None:
    first = _upload(db_session)
    first.status = ImportBatchStatus.FAILED
    db_session.commit()

    second = _upload(db_session)

    assert second.id != first.id
    assert second.status is ImportBatchStatus.UPLOADED


def test_store_upload_reuses_a_saved_mapping(db_session: Session, upload_dir: Path) -> None:
    saved = {
        "external_order_id": "ColX",
        "order_date": "ColY",
        "order_amount": "ColZ",
    }
    service.save_mapping_for_partner(
        db_session, source_type=ORDERS, partner="amazon", mapping=saved, user_id=None
    )
    db_session.commit()

    batch = _upload(db_session, content=b"ColX,ColY,ColZ\nA-1,2026-01-05,10.00\n")

    assert batch.status is ImportBatchStatus.UPLOADED
    assert batch.column_mapping == saved


# --- update_mapping --------------------------------------------------------


def test_update_mapping_completes_and_saves_for_partner(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session, content=UNMAPPED_CSV)
    assert batch.status is ImportBatchStatus.MAPPING_REQUIRED

    updated = service.update_mapping(
        db_session,
        batch,
        mapping={
            "external_order_id": "ColX",
            "order_date": "ColY",
        },
        save_for_partner=True,
        user_id=None,
    )

    assert updated.status is ImportBatchStatus.MAPPING_REQUIRED  # order_amount still missing
    saved = db_session.scalar(select(ImportColumnMapping))
    assert saved is not None
    assert saved.partner == "amazon"
    assert saved.mapping == {"external_order_id": "ColX", "order_date": "ColY"}


def test_update_mapping_marks_a_complete_mapping_ready(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session, content=UNMAPPED_CSV)
    assert batch.status is ImportBatchStatus.MAPPING_REQUIRED

    updated = service.update_mapping(
        db_session,
        batch,
        mapping={
            "external_order_id": "ColX",
            "order_date": "ColY",
            "order_amount": "ColZ",
        },
        save_for_partner=False,
        user_id=None,
    )

    assert updated.status is ImportBatchStatus.UPLOADED
    assert updated.column_mapping is not None
    assert db_session.scalar(select(ImportColumnMapping)) is None


def test_update_mapping_rejects_an_unknown_field(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session, content=UNMAPPED_CSV)

    with pytest.raises(MappingError):
        service.update_mapping(
            db_session,
            batch,
            mapping={"not_a_field": "ColX"},
            save_for_partner=False,
            user_id=None,
        )


@pytest.mark.parametrize(
    "status", [ImportBatchStatus.PROCESSING, ImportBatchStatus.COMPLETED]
)
def test_update_mapping_is_blocked_once_locked(
    db_session: Session, upload_dir: Path, status: ImportBatchStatus
) -> None:
    batch = _upload(db_session)
    batch.status = status
    db_session.commit()

    with pytest.raises(BatchStateError):
        service.update_mapping(
            db_session,
            batch,
            mapping={"external_order_id": "Order ID"},
            save_for_partner=False,
            user_id=None,
        )


# --- process_import --------------------------------------------------------


def test_process_import_stores_rows_and_counts(db_session: Session, upload_dir: Path) -> None:
    batch = _upload(db_session, content=MIXED_CSV)

    processed = service.process_import(db_session, batch)

    assert processed.status is ImportBatchStatus.COMPLETED
    assert processed.total_rows == 2
    assert processed.processed_rows == 1
    assert processed.failed_rows == 1
    assert processed.started_at is not None
    assert processed.completed_at is not None


def test_process_import_preserves_raw_and_normalizes_valid_rows(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session, content=MIXED_CSV)
    service.process_import(db_session, batch)

    records, total = service.list_records(db_session, batch)
    assert total == 2

    valid, invalid = records
    assert valid.row_number == 1
    assert valid.is_valid is True
    assert valid.raw_data == {
        "Order ID": "A-1",
        "Order Date": "2026-01-05",
        "Order Amount": "1,234.56",
    }
    assert valid.normalized_data is not None
    assert valid.normalized_data["order_amount"] == "1234.56"
    assert valid.external_reference == "A-1"

    # The raw value is preserved even though it could not be interpreted.
    assert invalid.is_valid is False
    assert invalid.raw_data["Order Amount"] == "N/A"
    assert invalid.normalized_data is not None
    assert invalid.normalized_data["order_amount"] is None
    assert invalid.validation_errors is not None
    assert "invalid_amount" in invalid.validation_errors


def test_process_import_requires_a_complete_mapping(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session)
    # Simulate a batch that lost its mapping after being marked ready.
    batch.column_mapping = {}
    db_session.commit()

    with pytest.raises(MappingError):
        service.process_import(db_session, batch)


def test_process_import_rejects_a_batch_awaiting_mapping(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session, content=UNMAPPED_CSV)

    with pytest.raises(BatchStateError):
        service.process_import(db_session, batch)


def test_process_import_rejects_an_already_completed_batch(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session)
    service.process_import(db_session, batch)

    with pytest.raises(BatchStateError):
        service.process_import(db_session, batch)


def test_process_import_can_run_on_a_failed_batch(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session)
    batch.status = ImportBatchStatus.FAILED
    db_session.commit()

    processed = service.process_import(db_session, batch)

    assert processed.status is ImportBatchStatus.COMPLETED


def test_process_import_discards_previous_rows_before_rerunning(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session)
    service.process_import(db_session, batch)
    batch.status = ImportBatchStatus.FAILED  # allow a rerun
    db_session.commit()

    service.process_import(db_session, batch)

    count = db_session.scalar(
        select(func.count())
        .select_from(RawImportedRecord)
        .where(RawImportedRecord.import_batch_id == batch.id)
    )
    assert count == 1


def test_process_import_writes_in_chunks(
    db_session: Session, upload_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IMPORT_BATCH_SIZE", "1")
    get_settings.cache_clear()

    content = (
        b"Order ID,Order Date,Order Amount\n"
        b"A-1,2026-01-05,10.00\n"
        b"A-2,2026-01-06,20.00\n"
        b"A-3,2026-01-07,30.00\n"
    )
    batch = _upload(db_session, content=content)

    processed = service.process_import(db_session, batch)

    assert processed.processed_rows == 3


# --- reads -----------------------------------------------------------------


def test_get_batch_raises_when_missing(db_session: Session, upload_dir: Path) -> None:
    with pytest.raises(BatchNotFoundError):
        service.get_batch(db_session, 999)


def test_build_preview_reports_columns_and_mapping(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session)

    preview = service.build_preview(batch, limit=5)

    assert preview["headers"] == ["Order ID", "Order Date", "Order Amount"]
    assert len(preview["rows"]) == 1
    assert preview["missing_required_fields"] == []
    assert preview["mapping_complete"] is True
    names = {field["name"] for field in preview["fields"]}
    assert {"external_order_id", "order_date", "order_amount"} <= names
    amount_field = next(
        field for field in preview["fields"] if field["name"] == "order_amount"
    )
    assert amount_field["mapped_header"] == "Order Amount"
    assert amount_field["required"] is True


def test_build_preview_lists_missing_required_fields(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session, content=UNMAPPED_CSV)

    preview = service.build_preview(batch, limit=5)

    assert preview["mapping_complete"] is False
    assert set(preview["missing_required_fields"]) == {
        "external_order_id",
        "order_date",
        "order_amount",
    }


def test_build_preview_reports_reused_mapping_as_saved(
    db_session: Session, upload_dir: Path
) -> None:
    """A mapping reused from the partner's approved one must not read as manual."""
    saved = {
        "external_order_id": "Ref No",
        "order_date": "Date",
        "order_amount": "Value",
    }
    batch = _upload(db_session, content=b"Ref No,Date,Value\nRF-1,2026-02-01,2500\n", partner="acme")
    service.update_mapping(
        db_session, batch, mapping=saved, save_for_partner=True, user_id=None
    )

    stored = service.load_saved_mapping(db_session, ORDERS, "acme")
    preview = service.build_preview(batch, limit=5, saved=stored)

    confidence = {field["name"]: field["confidence"] for field in preview["fields"]}
    assert confidence["external_order_id"] == "saved"
    assert confidence["order_amount"] == "saved"


def test_list_batches_filters_by_partner(db_session: Session, upload_dir: Path) -> None:
    _upload(db_session, partner="amazon")
    _upload(db_session, partner="flipkart")

    amazon = service.list_batches(db_session, partner="amazon")

    assert len(amazon) == 1
    assert amazon[0].marketplace == "amazon"


def test_list_batches_filters_by_status(db_session: Session, upload_dir: Path) -> None:
    _upload(db_session)
    _upload(db_session, content=UNMAPPED_CSV, partner="flipkart")

    ready = service.list_batches(db_session, status=ImportBatchStatus.UPLOADED)

    assert len(ready) == 1
    assert ready[0].status is ImportBatchStatus.UPLOADED


def test_list_records_can_return_only_invalid_rows(
    db_session: Session, upload_dir: Path
) -> None:
    batch = _upload(db_session, content=MIXED_CSV)
    service.process_import(db_session, batch)

    invalid, total = service.list_records(db_session, batch, only_invalid=True)

    assert total == 1
    assert invalid[0].is_valid is False
