"""Import orchestration.

This is the only module in :mod:`app.imports` that touches the database. It
wires the parser, the mapping layer and the normalizer together and owns the
batch lifecycle:

``uploaded``
    The file parsed cleanly and every required field is mapped, so it is ready
    to be processed.
``mapping_required``
    At least one required field could not be resolved; a human must map it.
``processing``
    Rows are being projected and written in batches.
``completed``
    Every row was written; see the counts for how many were rejected.
``failed``
    Processing aborted; the message on the batch says why.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.imports import mapping as mapping_layer
from app.imports import normalizer, parser
from app.imports.errors import (
    BatchNotFoundError,
    BatchStateError,
    DuplicateImportError,
    EmptyFileError,
    FileTooLargeError,
    InvalidFileError,
    InvalidRequestError,
    SourceTypeNotSupportedError,
)
from app.imports.fields import (
    SUPPORTED_SOURCE_TYPES,
    fields_for_source,
    required_fields_for_source,
)
from app.models import (
    ImportBatch,
    ImportBatchStatus,
    ImportColumnMapping,
    ImportSourceType,
    RawImportedRecord,
    UploadedFile,
)

#: Characters kept when building the on-disk filename.
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

#: Longest diagnostic kept on ``ImportBatch.error_message``.
_MAX_ERROR_MESSAGE = 2000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Upload ----------------------------------------------------------------


def store_upload(
    db: Session,
    *,
    filename: str,
    content: bytes,
    content_type: str | None,
    source_type: ImportSourceType,
    partner: str,
    user_id: int | None,
) -> ImportBatch:
    """Validate, store and register an uploaded file as a new import batch.

    The file is parsed *before* anything is written to disk, so a malformed or
    unsupported file leaves no trace. Identical bytes for the same source and
    partner are rejected rather than creating a second batch — unless the only
    earlier attempt failed, in which case re-uploading is how an operator
    retries it.
    """
    assert_supported_source_type(source_type)

    partner = partner.strip()
    if not partner:
        raise InvalidRequestError("A partner name is required.")

    settings = get_settings()

    # Extension first: "this is a PDF" is a more useful complaint than "empty".
    parser.detect_extension(filename)

    if not content:
        raise EmptyFileError("The uploaded file is empty.")

    if len(content) > settings.max_upload_size_bytes:
        raise FileTooLargeError(
            f"The file is {len(content)} bytes, which exceeds the "
            f"{settings.max_upload_size_bytes} byte limit."
        )

    checksum = hashlib.sha256(content).hexdigest()

    duplicate = _find_duplicate(db, checksum, source_type, partner)
    if duplicate is not None:
        raise DuplicateImportError(
            f"This exact file has already been uploaded for {partner!r} "
            f"(import {duplicate.id}).",
            existing_batch_id=duplicate.id,
        )

    table = parser.parse_bytes(filename, content)
    stored_path = _write_file(settings.upload_storage_path, checksum, filename, content)

    uploaded_file = UploadedFile(
        original_filename=Path(filename).name,
        storage_path=str(stored_path),
        content_type=content_type,
        size_bytes=len(content),
        checksum_sha256=checksum,
        uploaded_by_user_id=user_id,
    )

    batch = ImportBatch(
        uploaded_file=uploaded_file,
        source_type=source_type,
        marketplace=partner,
        created_by_user_id=user_id,
        total_rows=table.row_count,
    )

    # A previously approved mapping is authoritative; otherwise the
    # deterministic suggestion is stored as the starting point. Either way the
    # batch is only marked ready when every required field is resolved, so an
    # uncertain mapping is never silently accepted.
    saved = load_saved_mapping(db, source_type, partner)
    suggestion = mapping_layer.suggest_mapping(source_type, table.headers, saved=saved)
    batch.column_mapping = dict(suggestion.mapping) or None
    batch.status = (
        ImportBatchStatus.UPLOADED
        if suggestion.is_complete
        else ImportBatchStatus.MAPPING_REQUIRED
    )

    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def assert_supported_source_type(source_type: ImportSourceType) -> None:
    """Reject source types that exist in the schema but are not handled yet."""
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise SourceTypeNotSupportedError(
            f"{source_type.value!r} imports are not supported yet."
        )


def _find_duplicate(
    db: Session,
    checksum: str,
    source_type: ImportSourceType,
    partner: str,
) -> ImportBatch | None:
    """Return the earlier batch for the same bytes, source and partner.

    A batch that previously *failed* is not treated as a duplicate: its partial
    output was already discarded and the file on disk is unchanged, so allowing
    the upload again is how an operator retries a failed import.
    """
    statement = (
        select(ImportBatch)
        .join(UploadedFile, ImportBatch.uploaded_file_id == UploadedFile.id)
        .where(
            UploadedFile.checksum_sha256 == checksum,
            ImportBatch.source_type == source_type,
            ImportBatch.marketplace == partner,
            ImportBatch.status != ImportBatchStatus.FAILED,
        )
        .order_by(ImportBatch.id)
        .limit(1)
    )
    return db.scalars(statement).first()


def _write_file(storage_root: Path, checksum: str, filename: str, content: bytes) -> Path:
    """Write the upload verbatim, bucketed by month, named by its checksum.

    Keeping the original bytes on disk is what makes raw values auditable and
    lets previews be re-read without trusting anything held in memory. The
    name is content-addressed, so writing the same file twice is a no-op.
    """
    directory = storage_root / _utcnow().strftime("%Y-%m")
    directory.mkdir(parents=True, exist_ok=True)

    target = directory / f"{checksum[:16]}-{_safe_filename(filename)}"
    if not target.exists():
        target.write_bytes(content)
    return target


def _safe_filename(filename: str) -> str:
    """Reduce an uploaded name to something safe to place on disk."""
    base = Path(filename or "").name
    cleaned = _UNSAFE_FILENAME.sub("_", base).strip("._")
    return (cleaned or "upload")[:120]


# --- Reads -----------------------------------------------------------------


def get_batch(db: Session, batch_id: int) -> ImportBatch:
    """Load one batch with its file metadata, or raise a not-found error."""
    batch = db.scalar(
        select(ImportBatch)
        .options(selectinload(ImportBatch.uploaded_file))
        .where(ImportBatch.id == batch_id)
    )
    if batch is None:
        raise BatchNotFoundError(batch_id)
    return batch


def list_batches(
    db: Session,
    *,
    status: ImportBatchStatus | None = None,
    source_type: ImportSourceType | None = None,
    partner: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ImportBatch]:
    """Return recent batches, newest first, optionally filtered."""
    statement = select(ImportBatch).options(selectinload(ImportBatch.uploaded_file))

    conditions = []
    if status is not None:
        conditions.append(ImportBatch.status == status)
    if source_type is not None:
        conditions.append(ImportBatch.source_type == source_type)
    if partner is not None:
        conditions.append(ImportBatch.marketplace == partner)
    if conditions:
        statement = statement.where(*conditions)

    statement = (
        statement.order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(statement).all())


def list_records(
    db: Session,
    batch: ImportBatch,
    *,
    only_invalid: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[RawImportedRecord], int]:
    """Return a page of a batch's stored rows plus the matching total."""
    conditions = [RawImportedRecord.import_batch_id == batch.id]
    if only_invalid:
        conditions.append(RawImportedRecord.is_valid.is_(False))

    total = db.scalar(
        select(func.count()).select_from(RawImportedRecord).where(*conditions)
    )
    statement = (
        select(RawImportedRecord)
        .where(*conditions)
        .order_by(RawImportedRecord.row_number)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(statement).all()), int(total or 0)


def read_table(batch: ImportBatch) -> parser.ParsedTable:
    """Re-parse the batch's stored file.

    Preview and processing both read the original bytes from disk rather than
    anything cached, so what is shown is always what was uploaded.
    """
    stored = batch.uploaded_file
    if stored is None or not stored.storage_path:
        raise InvalidFileError("The stored file for this import is missing.")

    path = Path(stored.storage_path)
    if not path.is_file():
        raise InvalidFileError(f"The stored file {path} is no longer available.")

    return parser.parse_bytes(stored.original_filename, path.read_bytes())


def build_preview(batch: ImportBatch, *, limit: int) -> dict[str, Any]:
    """Describe the uploaded columns, sample rows and current mapping."""
    table = read_table(batch)
    current = {
        name: header
        for name, header in (batch.column_mapping or {}).items()
        if header in table.headers
    }
    required = set(required_fields_for_source(batch.source_type))

    # Recomputing the suggestion tells the UI how each auto-mapped column was
    # recognised; anything the operator changed by hand is reported as manual.
    suggestion = mapping_layer.suggest_mapping(batch.source_type, table.headers, saved=None)

    fields = []
    for field in fields_for_source(batch.source_type):
        header = current.get(field.name)
        if header is None:
            confidence = None
        elif suggestion.mapping.get(field.name) == header:
            confidence = suggestion.confidence_for(field.name)
        else:
            confidence = mapping_layer.CONFIDENCE_MANUAL

        fields.append(
            {
                "name": field.name,
                "label": field.label,
                "kind": field.kind,
                "required": field.name in required,
                "mapped_header": header,
                "confidence": confidence,
            }
        )

    mapped_headers = set(current.values())
    missing_required = sorted(required - set(current))

    return {
        "headers": table.headers,
        "rows": table.sample(limit),
        "fields": fields,
        "unmapped_headers": [h for h in table.headers if h not in mapped_headers],
        "missing_required_fields": missing_required,
        "mapping_complete": not missing_required,
    }


# --- Saved mappings --------------------------------------------------------


def load_saved_mapping(
    db: Session, source_type: ImportSourceType, partner: str
) -> dict[str, str] | None:
    """Return the approved mapping for this source/partner pair, if any."""
    if not partner:
        return None

    saved = db.scalar(
        select(ImportColumnMapping).where(
            ImportColumnMapping.source_type == source_type,
            ImportColumnMapping.partner == partner,
        )
    )
    return dict(saved.mapping) if saved is not None else None


def save_mapping_for_partner(
    db: Session,
    *,
    source_type: ImportSourceType,
    partner: str,
    mapping: Mapping[str, str],
    user_id: int | None,
) -> None:
    """Create or replace the approved mapping for a source/partner pair."""
    existing = db.scalar(
        select(ImportColumnMapping).where(
            ImportColumnMapping.source_type == source_type,
            ImportColumnMapping.partner == partner,
        )
    )

    if existing is None:
        db.add(
            ImportColumnMapping(
                source_type=source_type,
                partner=partner,
                mapping=dict(mapping),
                created_by_user_id=user_id,
            )
        )
    else:
        existing.mapping = dict(mapping)
        existing.created_by_user_id = user_id


# --- Mutation --------------------------------------------------------------


def update_mapping(
    db: Session,
    batch: ImportBatch,
    *,
    mapping: Mapping[str, str | None],
    save_for_partner: bool,
    user_id: int | None,
) -> ImportBatch:
    """Replace the batch's mapping with an operator-approved one.

    The mapping is frozen once processing starts (and after it finishes), since
    changing it mid-run would leave the stored rows inconsistent with the
    mapping recorded on the batch.
    """
    if batch.status in (ImportBatchStatus.PROCESSING, ImportBatchStatus.COMPLETED):
        raise BatchStateError(
            "The mapping cannot be changed while an import is processing or "
            "after it has been processed."
        )

    table = read_table(batch)
    validated = mapping_layer.validate_mapping(batch.source_type, table.headers, mapping)

    batch.column_mapping = validated.mapping or None
    batch.status = (
        ImportBatchStatus.UPLOADED
        if validated.is_complete
        else ImportBatchStatus.MAPPING_REQUIRED
    )

    if save_for_partner and batch.marketplace and validated.mapping:
        save_mapping_for_partner(
            db,
            source_type=batch.source_type,
            partner=batch.marketplace,
            mapping=validated.mapping,
            user_id=user_id,
        )

    db.commit()
    db.refresh(batch)
    return batch


def process_import(db: Session, batch: ImportBatch) -> ImportBatch:
    """Project every row onto the canonical fields and store the result.

    Rows are written in chunks of ``IMPORT_BATCH_SIZE`` so a large file does not
    need to be held in memory or committed in one transaction.
    """
    if batch.status not in (ImportBatchStatus.UPLOADED, ImportBatchStatus.FAILED):
        raise BatchStateError(
            "Only an import that is ready to process (or one that previously "
            "failed) can be processed."
        )

    table = read_table(batch)
    validated = mapping_layer.validate_mapping(
        batch.source_type, table.headers, batch.column_mapping, require_complete=True
    )

    # A failed run may have written part of its output. Those rows are derived
    # from the stored file and the stored file itself is never modified, so
    # discarding them and projecting again cannot lose source data.
    db.execute(
        delete(RawImportedRecord).where(RawImportedRecord.import_batch_id == batch.id)
    )

    batch.status = ImportBatchStatus.PROCESSING
    batch.started_at = _utcnow()
    batch.completed_at = None
    batch.error_message = None
    batch.total_rows = table.row_count
    batch.processed_rows = 0
    batch.failed_rows = 0
    db.commit()

    chunk_size = max(1, get_settings().import_batch_size)
    processed = 0
    failed = 0
    chunk: list[RawImportedRecord] = []
    batch_id = batch.id

    try:
        for position in range(table.row_count):
            raw_data = table.row_as_mapping(position)
            result = normalizer.normalize_row(
                mapping_layer.map_row(raw_data, validated.mapping), batch.source_type
            )

            chunk.append(
                RawImportedRecord(
                    import_batch_id=batch_id,
                    row_number=position + 1,
                    raw_data=raw_data,
                    normalized_data=result.normalized or None,
                    external_reference=normalizer.external_reference(result.normalized),
                    is_valid=result.is_valid,
                    validation_errors=(
                        json.dumps([issue.as_dict() for issue in result.issues])
                        if result.issues
                        else None
                    ),
                )
            )

            if result.is_valid:
                processed += 1
            else:
                failed += 1

            if len(chunk) >= chunk_size:
                db.add_all(chunk)
                db.commit()
                chunk = []

        if chunk:
            db.add_all(chunk)
            db.commit()
    except Exception as exc:
        _mark_failed(db, batch_id, exc, processed=processed, failed=failed)
        raise

    batch.status = ImportBatchStatus.COMPLETED
    batch.completed_at = _utcnow()
    batch.processed_rows = processed
    batch.failed_rows = failed
    db.commit()
    db.refresh(batch)
    return batch


def _mark_failed(
    db: Session, batch_id: int, exc: Exception, *, processed: int, failed: int
) -> None:
    """Record why processing aborted, without masking the original error."""
    db.rollback()

    batch = db.get(ImportBatch, batch_id)
    if batch is None:  # pragma: no cover - defensive
        return

    batch.status = ImportBatchStatus.FAILED
    batch.completed_at = _utcnow()
    batch.processed_rows = processed
    batch.failed_rows = failed
    batch.error_message = (str(exc) or exc.__class__.__name__)[:_MAX_ERROR_MESSAGE]
    db.commit()
