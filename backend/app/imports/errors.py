"""Exceptions raised by the import pipeline.

Each one maps to a specific HTTP status in the API layer, so the pipeline itself
stays free of web concerns.
"""


class ImportPipelineError(Exception):
    """Base class for every import failure."""


class SourceTypeNotSupportedError(ImportPipelineError):
    """The requested source type is declared but not handled yet."""


class InvalidRequestError(ImportPipelineError):
    """A required part of the request is missing or unusable."""


class UnsupportedFileTypeError(ImportPipelineError):
    """The uploaded file extension is not supported."""


class FileTooLargeError(ImportPipelineError):
    """The uploaded file exceeds the configured size limit."""


class InvalidFileError(ImportPipelineError):
    """The file could not be read as a tabular CSV/XLSX file."""


class EmptyFileError(InvalidFileError):
    """The file contains no header row or no data rows."""


class DuplicateImportError(ImportPipelineError):
    """The exact same file was already uploaded for this source and partner."""

    def __init__(self, message: str, *, existing_batch_id: int) -> None:
        super().__init__(message)
        self.existing_batch_id = existing_batch_id


class MappingError(ImportPipelineError):
    """The supplied column mapping is invalid or incomplete."""


class BatchNotFoundError(ImportPipelineError):
    """No import batch exists with the requested id."""

    def __init__(self, batch_id: int) -> None:
        super().__init__(f"Import {batch_id} was not found.")
        self.batch_id = batch_id


class BatchStateError(ImportPipelineError):
    """The requested operation is not valid for the batch's current status.

    For example, re-processing a batch that has already completed would append
    a second copy of every row.
    """
