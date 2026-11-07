"""File upload, import batch and raw record models.

These tables record *what was ingested* and *how it went*. The parsing,
mapping and normalisation logic lives in :mod:`app.imports`; the models only
describe the shape of the stored data.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import portable_enum
from app.models.enums import ImportBatchStatus, ImportSourceType

if TYPE_CHECKING:
    from app.models.reconciliation import ReconciliationResult
    from app.models.settlement import SettlementRecord
    from app.models.user import User


class UploadedFile(Base, TimestampMixin):
    """Metadata for a file supplied by a user.

    Only the description of the file is persisted; the bytes are not held in
    the database.
    """

    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(primary_key=True)

    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    uploaded_by: Mapped["User | None"] = relationship(
        back_populates="uploaded_files",
        foreign_keys=[uploaded_by_user_id],
    )
    # Mirrors ON DELETE CASCADE: a batch cannot outlive the file it describes.
    import_batches: Mapped[list["ImportBatch"]] = relationship(
        back_populates="uploaded_file",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<UploadedFile id={self.id} filename={self.original_filename!r}>"


class ImportBatch(Base, TimestampMixin):
    """One import run over a single uploaded file."""

    __tablename__ = "import_batches"
    __table_args__ = (Index("ix_import_batches_source_status", "source_type", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    uploaded_file_id: Mapped[int] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[ImportSourceType] = mapped_column(
        portable_enum(ImportSourceType, "import_source_type"),
        nullable=False,
    )
    #: The partner/marketplace the file came from. Also the scope key for the
    #: saved column mappings in :class:`~app.models.mappings.ImportColumnMapping`.
    marketplace: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[ImportBatchStatus] = mapped_column(
        portable_enum(ImportBatchStatus, "import_batch_status"),
        nullable=False,
        default=ImportBatchStatus.UPLOADED,
        server_default=ImportBatchStatus.UPLOADED.value,
    )

    #: Approved canonical-field -> source-header mapping for this batch. Kept on
    #: the batch so a re-run is reproducible even if the saved mapping changes.
    column_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    total_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    processed_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    failed_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    uploaded_file: Mapped["UploadedFile"] = relationship(back_populates="import_batches")
    created_by: Mapped["User | None"] = relationship(
        back_populates="import_batches",
        foreign_keys=[created_by_user_id],
    )
    raw_records: Mapped[list["RawImportedRecord"]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
    )
    settlement_records: Mapped[list["SettlementRecord"]] = relationship(
        back_populates="import_batch",
    )
    reconciliation_results: Mapped[list["ReconciliationResult"]] = relationship(
        back_populates="import_batch",
    )

    def __repr__(self) -> str:
        return f"<ImportBatch id={self.id} source_type={self.source_type} status={self.status}>"


class RawImportedRecord(Base):
    """A single source row, preserved verbatim for traceability.

    ``raw_data`` is the original row exactly as read from the file and is never
    rewritten. ``normalized_data`` is the canonical-field projection produced
    during processing, so the source of every stored value stays auditable.

    Only ``created_at`` is tracked: raw rows are immutable once written.
    """

    __tablename__ = "raw_imported_records"
    __table_args__ = (Index("ix_raw_imported_records_batch_row", "import_batch_id", "row_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    #: Canonical field -> normalized value, produced by the mapping/normalizer.
    normalized_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    is_valid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    #: JSON-encoded list of ``{field, code, message}`` entries. Stored as text
    #: because the column predates this feature; the API decodes it.
    validation_errors: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    import_batch: Mapped["ImportBatch"] = relationship(back_populates="raw_records")
    settlement_records: Mapped[list["SettlementRecord"]] = relationship(
        back_populates="raw_record",
    )

    def __repr__(self) -> str:
        return f"<RawImportedRecord id={self.id} batch_id={self.import_batch_id} row={self.row_number}>"
