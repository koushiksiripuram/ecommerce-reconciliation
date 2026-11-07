"""Tests for row-level interpretation and validation."""

from datetime import date
from decimal import Decimal

import pytest

from app.imports import normalizer
from app.models.enums import ImportSourceType

ORDERS = ImportSourceType.ORDERS


# --- parse_amount ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.56", Decimal("1234.56")),
        ("\u20b91,234.56", Decimal("1234.56")),  # rupee symbol + thousands
        ("INR 1,234.56", Decimal("1234.56")),
        ("1.234,56", Decimal("1234.56")),  # European grouping
        ("1,234", Decimal("1234")),  # grouping, no decimals
        ("0,5", Decimal("0.5")),  # comma as decimal
        ("12.345.678", Decimal("12345678")),  # repeated decimals are groups
        ("-50", Decimal("-50")),
        ("(500.00)", Decimal("-500.00")),  # accounting negative
    ],
)
def test_parse_amount_understands_common_formats(raw: str, expected: Decimal) -> None:
    assert normalizer.parse_amount(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "N/A", "abc", "-", "(not a number)"])
def test_parse_amount_returns_none_for_unusable_values(raw: str) -> None:
    assert normalizer.parse_amount(raw) is None


# --- parse_date ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-01-05", date(2026, 1, 5)),
        ("2026/01/05", date(2026, 1, 5)),
        ("05-01-2026", date(2026, 1, 5)),
        ("05.01.2026", date(2026, 1, 5)),
        ("5 Jan 2026", date(2026, 1, 5)),
        ("January 5, 2026", date(2026, 1, 5)),
        # Day-first is the documented convention for ambiguous dates.
        ("01/02/2026", date(2026, 2, 1)),
    ],
)
def test_parse_date_understands_common_formats(raw: str, expected: date) -> None:
    assert normalizer.parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "not a date", "32/13/2026"])
def test_parse_date_returns_none_for_unusable_values(raw: str) -> None:
    assert normalizer.parse_date(raw) is None


# --- normalize_row ---------------------------------------------------------


def test_normalize_row_converts_amounts_and_dates() -> None:
    result = normalizer.normalize_row(
        {
            "external_order_id": "A-1",
            "order_date": "05/01/2026",
            "order_amount": "\u20b91,234.56",
        },
        ORDERS,
    )

    assert result.is_valid is True
    assert result.normalized == {
        "external_order_id": "A-1",
        "order_date": "2026-01-05",
        "order_amount": "1234.56",
    }


def test_normalize_row_strips_text_values() -> None:
    result = normalizer.normalize_row(
        {"external_order_id": "A-1", "customer_name": "  Bob  "}, ORDERS
    )

    assert result.normalized["customer_name"] == "Bob"


def test_normalize_row_flags_an_invalid_amount_once() -> None:
    result = normalizer.normalize_row(
        {
            "external_order_id": "A-1",
            "order_date": "2026-01-05",
            "order_amount": "N/A",
        },
        ORDERS,
    )

    assert result.is_valid is False
    assert [issue.code for issue in result.issues] == [normalizer.CODE_INVALID_AMOUNT]
    assert result.normalized["order_amount"] is None


def test_normalize_row_flags_an_invalid_date() -> None:
    result = normalizer.normalize_row(
        {
            "external_order_id": "A-1",
            "order_date": "not a date",
            "order_amount": "10.00",
        },
        ORDERS,
    )

    assert [issue.code for issue in result.issues] == [normalizer.CODE_INVALID_DATE]


def test_normalize_row_flags_a_required_field_that_is_empty() -> None:
    result = normalizer.normalize_row(
        {"external_order_id": "", "order_date": "2026-01-05", "order_amount": "10.00"},
        ORDERS,
    )

    assert result.is_valid is False
    assert [issue.code for issue in result.issues] == [normalizer.CODE_REQUIRED]
    assert result.issues[0].field == "external_order_id"


def test_normalize_row_ignores_missing_optional_fields() -> None:
    result = normalizer.normalize_row(
        {"external_order_id": "A-1", "order_date": "2026-01-05", "order_amount": "10.00"},
        ORDERS,
    )

    assert result.is_valid is True


# --- external_reference ----------------------------------------------------


def test_external_reference_prefers_the_order_id() -> None:
    assert (
        normalizer.external_reference(
            {"external_order_id": "A-1", "transaction_reference": "T-9"}
        )
        == "A-1"
    )


def test_external_reference_falls_back_to_the_transaction_reference() -> None:
    assert normalizer.external_reference({"transaction_reference": "T-9"}) == "T-9"


def test_external_reference_is_none_when_nothing_is_present() -> None:
    assert normalizer.external_reference({"customer_name": "Bob"}) is None


def test_external_reference_is_truncated_to_the_column_width() -> None:
    reference = normalizer.external_reference({"external_order_id": "x" * 200})

    assert reference is not None
    assert len(reference) == normalizer.EXTERNAL_REFERENCE_MAX_LENGTH
