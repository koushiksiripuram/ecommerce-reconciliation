"""Import endpoints: upload, preview, mapping approval and processing.

These are thin wrappers over :mod:`app.imports.service`; all parsing, mapping
and normalisation lives there. The router's job is to translate HTTP requests
into service calls and the service's :class:`~app.imports.errors.ImportPipelineError`
hierarchy into HTTP responses (registered in :mod:`app.main`).

Reads require any authenticated user. Mutating the import lifecycle (upload,
mapping, processing) is restricted to the two internal finance roles.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.roles import RoleName
from app.db.session import get_db
from app.imports import service
from app.imports.fields import (
    SOURCE_TYPE_LABELS,
    SUPPORTED_SOURCE_TYPES,
    required_fields_for_source,
)
from app.models import ImportBatchStatus, ImportSourceType, User
from app.schemas.imports import (
    ImportBatchRead,
    ImportPreviewRead,
    ImportRecordPage,
    ImportRecordRead,
    MappingRequest,
    SourceTypeRead,
)

router = APIRouter(prefix="/imports", tags=["imports"])

#: Dependency for endpoints that mutate the import lifecycle.
ImportOperator = Annotated[
    User,
    Depends(require_roles(RoleName.FINANCE_EXECUTIVE, RoleName.CO_FOUNDER)),
]

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/source-types", response_model=list[SourceTypeRead])
def list_source_types(user: CurrentUser) -> list[SourceTypeRead]:
    """List the source types the importer accepts, with their required fields."""
    return [
        SourceTypeRead(
            value=source_type.value,
            label=SOURCE_TYPE_LABELS[source_type],
            required_fields=list(required_fields_for_source(source_type)),
        )
        for source_type in SUPPORTED_SOURCE_TYPES
    ]


@router.post("", response_model=ImportBatchRead, status_code=status.HTTP_201_CREATED)
def upload_import(
    user: ImportOperator,
    db: DbSession,
    file: Annotated[UploadFile, File(description="A CSV or XLSX file to import.")],
    source_type: Annotated[ImportSourceType, Form()],
    partner: Annotated[str, Form()],
) -> ImportBatchRead:
    """Upload a file and register it as a new import batch."""
    content = file.file.read()
    batch = service.store_upload(
        db,
        filename=file.filename or "",
        content=content,
        content_type=file.content_type,
        source_type=source_type,
        partner=partner,
        user_id=user.id,
    )
    return ImportBatchRead.from_model(batch)


@router.get("", response_model=list[ImportBatchRead])
def list_imports(
    user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[ImportBatchStatus | None, Query(alias="status")] = None,
    source_type: Annotated[ImportSourceType | None, Query()] = None,
    partner: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ImportBatchRead]:
    """List recent imports, newest first, with optional filters."""
    batches = service.list_batches(
        db,
        status=status_filter,
        source_type=source_type,
        partner=partner,
        limit=limit,
        offset=offset,
    )
    return [ImportBatchRead.from_model(batch) for batch in batches]


@router.get("/{batch_id}", response_model=ImportBatchRead)
def get_import(batch_id: int, user: CurrentUser, db: DbSession) -> ImportBatchRead:
    """Return one import batch."""
    return ImportBatchRead.from_model(service.get_batch(db, batch_id))


@router.get("/{batch_id}/preview", response_model=ImportPreviewRead)
def preview_import(batch_id: int, user: CurrentUser, db: DbSession) -> ImportPreviewRead:
    """Return the uploaded columns, sample rows and the mapping under review."""
    batch = service.get_batch(db, batch_id)
    saved = service.load_saved_mapping(db, batch.source_type, batch.marketplace or "")
    preview = service.build_preview(
        batch, limit=get_settings().import_preview_rows, saved=saved
    )
    return ImportPreviewRead(batch=ImportBatchRead.from_model(batch), **preview)


@router.put("/{batch_id}/mapping", response_model=ImportBatchRead)
def update_import_mapping(
    batch_id: int,
    payload: MappingRequest,
    user: ImportOperator,
    db: DbSession,
) -> ImportBatchRead:
    """Replace a batch's mapping with an operator-approved one."""
    batch = service.get_batch(db, batch_id)
    updated = service.update_mapping(
        db,
        batch,
        mapping=payload.mapping,
        save_for_partner=payload.save_for_partner,
        user_id=user.id,
    )
    return ImportBatchRead.from_model(updated)


@router.post("/{batch_id}/process", response_model=ImportBatchRead)
def process_import(batch_id: int, user: ImportOperator, db: DbSession) -> ImportBatchRead:
    """Project every row of a ready batch onto the canonical fields."""
    batch = service.get_batch(db, batch_id)
    processed = service.process_import(db, batch)
    return ImportBatchRead.from_model(processed)


@router.get("/{batch_id}/records", response_model=ImportRecordPage)
def list_import_records(
    batch_id: int,
    user: CurrentUser,
    db: DbSession,
    only_invalid: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ImportRecordPage:
    """Page through the rows stored for a processed batch."""
    batch = service.get_batch(db, batch_id)
    records, total = service.list_records(
        db, batch, only_invalid=only_invalid, limit=limit, offset=offset
    )
    rows = [
        ImportRecordRead(
            row_number=record.row_number,
            external_reference=record.external_reference,
            is_valid=record.is_valid,
            raw_data=record.raw_data,
            normalized_data=record.normalized_data,
            errors=ImportRecordRead.decode_errors(record.validation_errors),
        )
        for record in records
    ]
    return ImportRecordPage(total=total, returned=len(rows), rows=rows)
