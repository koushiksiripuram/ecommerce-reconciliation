"""CSV and XLSX parsing.

The parser's only job is to turn a file's bytes into a header row plus string
rows. It knows nothing about canonical fields, mapping or the database, which
is what lets the mapping layer be tested against plain lists of header names.

Values are kept as text exactly as read: for XLSX this means a cell's value is
rendered to its plain text form (a date becomes its ISO representation) instead
of being reformatted for display, so nothing is silently altered.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import load_workbook

from app.imports.errors import EmptyFileError, InvalidFileError, UnsupportedFileTypeError

CSV_EXTENSION = ".csv"
XLSX_EXTENSION = ".xlsx"

#: File extensions the import API accepts, keyed by extension.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (CSV_EXTENSION, XLSX_EXTENSION)

#: Delimiters tried when sniffing a CSV dialect.
_CSV_DELIMITERS = ",;\t|"

# How many bytes are handed to the dialect sniffer.
_SNIFF_SAMPLE_BYTES = 8192


@dataclass(frozen=True)
class ParsedTable:
    """A parsed file: a header row and the data rows beneath it."""

    headers: list[str]
    rows: list[list[str]]
    extension: str

    @property
    def row_count(self) -> int:
        """Number of data rows (the header row is not counted)."""
        return len(self.rows)

    def row_as_mapping(self, index: int) -> dict[str, str]:
        """Return row ``index`` keyed by header, padded/truncated to width."""
        row = self.rows[index]
        return {
            header: (row[position] if position < len(row) else "")
            for position, header in enumerate(self.headers)
        }

    def sample(self, limit: int) -> list[dict[str, str]]:
        """Return the first ``limit`` rows keyed by header."""
        return [self.row_as_mapping(index) for index in range(min(limit, self.row_count))]


def detect_extension(filename: str) -> str:
    """Return the lower-cased extension, or raise if it is not supported."""
    extension = Path(filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        raise UnsupportedFileTypeError(
            f"Unsupported file type {extension or '(none)'}. Supported types: {supported}."
        )
    return extension


def parse_bytes(filename: str, content: bytes) -> ParsedTable:
    """Parse an uploaded file into headers and rows.

    Raises one of the pipeline errors for empty, unreadable or header-only
    files; the API layer turns those into 4xx responses.
    """
    if not content:
        raise EmptyFileError("The uploaded file is empty.")

    extension = detect_extension(filename)

    if extension == CSV_EXTENSION:
        headers, rows = _parse_csv(content)
    else:
        headers, rows = _parse_xlsx(content)

    headers, rows = _trim_trailing_empty_columns(headers, rows)
    _validate_headers(headers)

    if not rows:
        raise EmptyFileError("The file contains a header row but no data rows.")

    return ParsedTable(headers=headers, rows=rows, extension=extension)


# --- CSV -------------------------------------------------------------------


def _parse_csv(content: bytes) -> tuple[list[str], list[list[str]]]:
    text = _decode(content)

    try:
        dialect: csv.Dialect | type[csv.Dialect] = csv.Sniffer().sniff(
            text[:_SNIFF_SAMPLE_BYTES], delimiters=_CSV_DELIMITERS
        )
    except csv.Error:
        # Single-column files and very short files defeat the sniffer; the
        # comma-separated dialect is the documented default.
        dialect = csv.excel

    try:
        records = list(csv.reader(io.StringIO(text, newline=""), dialect))
    except csv.Error as exc:
        raise InvalidFileError(f"The CSV file could not be parsed: {exc}") from exc

    if not records:
        raise EmptyFileError("The CSV file is empty.")

    header_row, *data_rows = records
    return list(header_row), [list(row) for row in data_rows]


def _decode(content: bytes) -> str:
    """Decode CSV bytes, tolerating the encodings exports actually use."""
    # utf-8-sig transparently drops the BOM Excel writes.
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InvalidFileError("The file is not valid UTF-8 or Windows-1252 text.")


# --- XLSX ------------------------------------------------------------------


def _parse_xlsx(content: bytes) -> tuple[list[str], list[list[str]]]:
    # read_only streams rows instead of building the whole grid; data_only
    # returns cached formula results rather than the formula text.
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises several unrelated exception types
        raise InvalidFileError(f"The XLSX file could not be read: {exc}") from exc

    try:
        sheet = workbook.active
        if sheet is None:
            raise EmptyFileError("The workbook contains no worksheets.")

        rows_iterator = sheet.iter_rows(values_only=True)
        header_row = next(rows_iterator, None)
        if header_row is None:
            raise EmptyFileError("The workbook is empty.")

        headers = [_cell_to_text(value) for value in header_row]
        rows: list[list[str]] = []
        for record in rows_iterator:
            cells = [_cell_to_text(value) for value in record]
            # Trailing rows Excel sometimes leaves behind carry no data.
            if all(cell == "" for cell in cells):
                continue
            rows.append(cells)
    finally:
        workbook.close()

    return headers, rows


def _cell_to_text(value: object) -> str:
    """Render an XLSX cell value as faithful, unambiguous text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, float):
        # repr() gives the shortest string that round-trips to the same float,
        # so 1234.56 stays "1234.56" instead of picking up binary noise.
        return repr(value)
    return str(value)


# --- Shared post-processing ------------------------------------------------


def _trim_trailing_empty_columns(
    headers: list[str], rows: list[list[str]]
) -> tuple[list[str], list[list[str]]]:
    """Drop unnamed trailing columns and align every row to the header width."""
    last_named = -1
    for position, header in enumerate(headers):
        if header.strip():
            last_named = position

    if last_named < 0:
        raise EmptyFileError("The file has no header row.")

    width = last_named + 1
    # Header text is trimmed (it is only ever used as a key, and stray spaces
    # would otherwise defeat alias matching). Cell values are left untouched so
    # what is stored as raw data is what the file contained.
    trimmed_headers = [header.strip() for header in headers[:width]]
    aligned_rows = [list(row[:width]) for row in rows]
    return trimmed_headers, aligned_rows


def _validate_headers(headers: list[str]) -> None:
    """Reject header rows that cannot be mapped unambiguously."""
    seen: dict[str, str] = {}
    duplicates: list[str] = []

    for header in headers:
        key = header.casefold()
        if key in seen:
            duplicates.append(header)
        else:
            seen[key] = header

    if duplicates:
        unique = sorted(set(duplicates))
        raise InvalidFileError(
            "The file has duplicate column names: " + ", ".join(repr(name) for name in unique)
        )
