"""Request and response schemas for the import API.

Responses are built from ORM objects by :meth:`ImportBatchRead.from_model`
rather than by attribute mapping, so exactly which fields leave the API is
explicit and easy to audit.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.imports.fields import SOURCE_TYPE_LABELS
from app.models import ImportBatch, ImportBatchStatus, ImportSourceType


class ImportBatchRead(BaseModel):
    """Summary of one import batch, including its row counts."""

    id: int
    source_type: ImportSourceType
    source_label: str
    partner: str | None
    status: ImportBatchStatus
    original_filename: str | None
    content_type: str | None
    size_bytes: int | None
    total_rows: int
    processed_rows: int
    failed_rows: int
    column_mapping: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime | None

    @classmethod
    def from_model(cls, batch: ImportBatch) -> ImportBatchRead:
        stored = batch.uploaded_file
        return cls(
            id=batch.id,
            source_type=batch.source_type,
            source_label=SOURCE_TYPE_LABELS.get(
                batch.source_type, batch.source_type.value
            ),
            partner=batch.marketplace,
            status=batch.status,
            original_filename=stored.original_filename if stored else None,
            content_type=stored.content_type if stored else None,
            size_bytes=stored.size_bytes if stored else None,
            total_rows=batch.total_rows,
            processed_rows=batch.processed_rows,
            failed_rows=batch.failed_rows,
            column_mapping=dict(batch.column_mapping) if batch.column_mapping else None,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            error_message=batch.error_message,
            created_at=batch.created_at,
        )


class ImportFieldRead(BaseModel):
    """One canonical field and how it is currently mapped for a batch."""

    name: str
    label: str
    kind: str
    required: bool
    mapped_header: str | None
    confidence: str | None


class ImportPreviewRead(BaseModel):
    """The uploaded columns, sample rows and the mapping under review."""

    batch: ImportBatchRead
    headers: list[str]
    rows: list[dict[str, str]]
    fields: list[ImportFieldRead]
    unmapped_headers: list[str]
    missing_required_fields: list[str]
    mapping_complete: bool


class MappingRequest(BaseModel):
    """A mapping submitted for review.

    Values may be ``null`` to clear a field. An incomplete mapping is accepted
    and leaves the batch in ``mapping_required``; only processing insists on a
    complete one.
    """

    mapping: dict[str, str | None] = Field(default_factory=dict)
    #: Persist this mapping as the default for the batch's source and partner.
    save_for_partner: bool = False


class ImportRowError(BaseModel):
    """One validation problem found while processing a row."""

    field: str
    code: str
    message: str


class ImportRecordRead(BaseModel):
    """A stored raw row together with its canonical projection."""

    row_number: int
    external_reference: str | None
    is_valid: bool
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any] | None
    errors: list[ImportRowError]

    @staticmethod
    def decode_errors(encoded: str | None) -> list[ImportRowError]:
        """Decode the JSON stored in ``validation_errors``."""
        if not encoded:
            return []
        try:
            decoded = json.loads(encoded)
        except (TypeError, ValueError):
            return []
        if not isinstance(decoded, list):
            return []
        return [
            ImportRowError(**entry)
            for entry in decoded
            if isinstance(entry, dict) and {"field", "code", "message"} <= set(entry)
        ]


class ImportRecordPage(BaseModel):
    """A page of stored rows, newest batch rows first by row number."""

    total: int
    returned: int
    rows: list[ImportRecordRead]


class SourceTypeRead(BaseModel):
    """A source type the import API accepts, for populating the UI."""

    value: str
    label: str
    required_fields: list[str]
