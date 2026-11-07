"""FastAPI application entry point."""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.imports.errors import (
    BatchNotFoundError,
    BatchStateError,
    DuplicateImportError,
    EmptyFileError,
    FileTooLargeError,
    ImportPipelineError,
    InvalidFileError,
    InvalidRequestError,
    MappingError,
    SourceTypeNotSupportedError,
    UnsupportedFileTypeError,
)

settings = get_settings()

#: HTTP status for each pipeline failure. Looked up along the error's MRO so a
#: more specific subclass (e.g. EmptyFileError) can override its parent.
_IMPORT_ERROR_STATUS: dict[type[ImportPipelineError], int] = {
    UnsupportedFileTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    FileTooLargeError: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    EmptyFileError: status.HTTP_400_BAD_REQUEST,
    InvalidFileError: status.HTTP_400_BAD_REQUEST,
    InvalidRequestError: status.HTTP_400_BAD_REQUEST,
    SourceTypeNotSupportedError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    MappingError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    BatchNotFoundError: status.HTTP_404_NOT_FOUND,
    BatchStateError: status.HTTP_409_CONFLICT,
    DuplicateImportError: status.HTTP_409_CONFLICT,
}


def _import_pipeline_error_handler(request: Request, exc: ImportPipelineError) -> JSONResponse:
    """Turn an import pipeline failure into an HTTP response.

    The pipeline itself stays web-agnostic; this is the single place that knows
    which status each failure maps to.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    for error_type in type(exc).__mro__:
        if error_type in _IMPORT_ERROR_STATUS:
            status_code = _IMPORT_ERROR_STATUS[error_type]
            break

    if isinstance(exc, DuplicateImportError):
        detail: object = {
            "message": str(exc),
            "existing_batch_id": exc.existing_batch_id,
        }
    else:
        detail = str(exc)

    return JSONResponse(status_code=status_code, content={"detail": detail})


app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_exception_handler(ImportPipelineError, _import_pipeline_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)
