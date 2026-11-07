"""Tests for the CSV/XLSX parser.

The parser is pure, so these tests need no database or filesystem beyond an
in-memory workbook.
"""

import io

import pytest
from openpyxl import Workbook

from app.imports import parser
from app.imports.errors import EmptyFileError, InvalidFileError, UnsupportedFileTypeError


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


# --- CSV -------------------------------------------------------------------


def test_parses_a_comma_separated_file() -> None:
    table = parser.parse_bytes("orders.csv", b"Order ID,Order Date\nA,2026-01-01\n")

    assert table.headers == ["Order ID", "Order Date"]
    assert table.row_count == 1
    assert table.row_as_mapping(0) == {"Order ID": "A", "Order Date": "2026-01-01"}
    assert table.extension == ".csv"


def test_sniffs_a_semicolon_delimiter() -> None:
    table = parser.parse_bytes("orders.csv", b"Order ID;Amount\nA;10.00\n")

    assert table.headers == ["Order ID", "Amount"]
    assert table.rows[0] == ["A", "10.00"]


def test_sniffs_a_tab_delimiter() -> None:
    table = parser.parse_bytes("orders.csv", b"Order ID\tAmount\nA\t10.00\n")

    assert table.headers == ["Order ID", "Amount"]


def test_strips_a_utf8_bom() -> None:
    table = parser.parse_bytes("orders.csv", "\ufeffOrder ID,Amount\nA,10\n".encode("utf-8"))

    assert table.headers[0] == "Order ID"


def test_decodes_windows_1252_text() -> None:
    table = parser.parse_bytes("orders.csv", "Customer Name\nCaf\u00e9\n".encode("cp1252"))

    assert table.rows[0][0] == "Caf\u00e9"


def test_trims_trailing_unnamed_columns() -> None:
    table = parser.parse_bytes("orders.csv", b"A,B,,\n1,2,,\n")

    assert table.headers == ["A", "B"]
    assert table.rows == [["1", "2"]]


def test_rejects_duplicate_headers() -> None:
    with pytest.raises(InvalidFileError, match="duplicate column names"):
        parser.parse_bytes("orders.csv", b"Amount,amount\n1,2\n")


def test_rejects_an_empty_file() -> None:
    with pytest.raises(EmptyFileError):
        parser.parse_bytes("orders.csv", b"")


def test_rejects_a_header_only_file() -> None:
    with pytest.raises(EmptyFileError, match="no data rows"):
        parser.parse_bytes("orders.csv", b"A,B\n")


def test_rejects_a_file_without_a_header_row() -> None:
    with pytest.raises(EmptyFileError):
        parser.parse_bytes("orders.csv", b",,\n1,2,3\n")


def test_rejects_an_unsupported_extension() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        parser.parse_bytes("statement.pdf", b"whatever")


def test_detect_extension_is_case_insensitive() -> None:
    assert parser.detect_extension("DATA.CSV") == ".csv"


def test_sample_respects_the_requested_limit() -> None:
    table = parser.parse_bytes("orders.csv", b"Order ID\nA\nB\nC\n")

    assert len(table.sample(2)) == 2
    assert len(table.sample(10)) == 3


# --- XLSX ------------------------------------------------------------------


def test_parses_an_xlsx_file() -> None:
    content = _xlsx_bytes(
        [["Order ID", "Order Date", "Order Amount"], ["X-1", "2026-01-01", 1234.56]]
    )

    table = parser.parse_bytes("orders.xlsx", content)

    assert table.extension == ".xlsx"
    assert table.headers == ["Order ID", "Order Date", "Order Amount"]
    # A float is rendered without binary noise, keeping the value faithful.
    assert table.rows[0] == ["X-1", "2026-01-01", "1234.56"]


def test_xlsx_date_cells_become_iso_text() -> None:
    from datetime import datetime

    content = _xlsx_bytes([["Order Date"], [datetime(2026, 1, 5, 9, 30)]])

    table = parser.parse_bytes("orders.xlsx", content)

    assert table.rows[0][0] == "2026-01-05 09:30:00"


def test_xlsx_blank_rows_are_skipped() -> None:
    content = _xlsx_bytes([["A", "B"], ["1", "2"], ["", ""]])

    table = parser.parse_bytes("orders.xlsx", content)

    assert table.row_count == 1


def test_rejects_an_unreadable_xlsx_file() -> None:
    with pytest.raises(InvalidFileError):
        parser.parse_bytes("orders.xlsx", b"not a real workbook")
