"""Tests for the mapping layer.

Suggestion and validation are pure functions over a list of header names, so
these need neither a database nor a file.
"""

import pytest

from app.imports import mapping
from app.imports.errors import MappingError
from app.models.enums import ImportSourceType

ORDERS = ImportSourceType.ORDERS
SETTLEMENTS = ImportSourceType.SETTLEMENTS


# --- suggest_mapping -------------------------------------------------------


def test_suggests_a_mapping_from_aliases() -> None:
    suggestion = mapping.suggest_mapping(
        ORDERS, ["Order ID", "Order Date", "Order Amount"]
    )

    assert suggestion.mapping == {
        "external_order_id": "Order ID",
        "order_date": "Order Date",
        "order_amount": "Order Amount",
    }
    assert suggestion.is_complete is True
    assert suggestion.missing_required == ()
    assert suggestion.confidence_for("external_order_id") == mapping.CONFIDENCE_ALIAS


def test_exact_canonical_names_are_marked_exact() -> None:
    suggestion = mapping.suggest_mapping(
        ORDERS, ["external_order_id", "order_date", "order_amount"]
    )

    assert suggestion.confidence_for("external_order_id") == mapping.CONFIDENCE_EXACT
    assert suggestion.is_complete is True


def test_a_saved_mapping_wins_over_everything_else() -> None:
    saved = {"external_order_id": "Custom Ref"}
    suggestion = mapping.suggest_mapping(
        ORDERS,
        ["Custom Ref", "Order Date", "Order Amount"],
        saved=saved,
    )

    assert suggestion.mapping["external_order_id"] == "Custom Ref"
    assert suggestion.confidence_for("external_order_id") == mapping.CONFIDENCE_SAVED


def test_a_saved_header_missing_from_the_file_is_ignored() -> None:
    saved = {"external_order_id": "Not In This File"}
    suggestion = mapping.suggest_mapping(
        ORDERS, ["Order ID", "Order Date", "Order Amount"], saved=saved
    )

    assert suggestion.mapping["external_order_id"] == "Order ID"
    assert suggestion.confidence_for("external_order_id") == mapping.CONFIDENCE_ALIAS


def test_unmapped_required_fields_leave_the_mapping_incomplete() -> None:
    suggestion = mapping.suggest_mapping(ORDERS, ["Foo", "Bar"])

    assert suggestion.is_complete is False
    assert set(suggestion.missing_required) == {
        "external_order_id",
        "order_date",
        "order_amount",
    }
    assert suggestion.mapping == {}


def test_headers_are_reported_as_unmapped_when_they_match_nothing() -> None:
    suggestion = mapping.suggest_mapping(
        ORDERS, ["Order ID", "Order Date", "Order Amount", "Internal Note"]
    )

    assert suggestion.unmapped_headers == ("Internal Note",)


def test_contains_tier_matches_a_longer_header() -> None:
    suggestion = mapping.suggest_mapping(ORDERS, ["Total Order Amount INR"])

    assert suggestion.mapping["order_amount"] == "Total Order Amount INR"
    assert suggestion.confidence_for("order_amount") == mapping.CONFIDENCE_CONTAINS


# --- validate_mapping ------------------------------------------------------


def test_validate_accepts_a_complete_mapping() -> None:
    validated = mapping.validate_mapping(
        ORDERS,
        ["A", "B", "C"],
        {"external_order_id": "A", "order_date": "B", "order_amount": "C"},
        require_complete=True,
    )

    assert validated.is_complete is True
    assert validated.mapping == {
        "external_order_id": "A",
        "order_date": "B",
        "order_amount": "C",
    }


def test_validate_reports_missing_required_without_raising() -> None:
    validated = mapping.validate_mapping(ORDERS, ["A"], {"external_order_id": "A"})

    assert validated.is_complete is False
    assert set(validated.missing_required) == {"order_date", "order_amount"}


def test_validate_raises_when_completeness_is_required() -> None:
    with pytest.raises(MappingError, match="incomplete"):
        mapping.validate_mapping(
            SETTLEMENTS, ["A"], {"transaction_reference": "A"}, require_complete=True
        )


def test_validate_skips_blank_headers() -> None:
    validated = mapping.validate_mapping(
        ORDERS, ["A"], {"external_order_id": "A", "order_date": None, "order_amount": "  "}
    )

    assert validated.mapping == {"external_order_id": "A"}


def test_validate_rejects_an_unknown_field() -> None:
    with pytest.raises(MappingError, match="Unknown canonical field"):
        mapping.validate_mapping(ORDERS, ["A"], {"not_a_field": "A"})


def test_validate_rejects_a_header_that_is_not_in_the_file() -> None:
    with pytest.raises(MappingError, match="not present in the file"):
        mapping.validate_mapping(ORDERS, ["A"], {"external_order_id": "Missing"})


def test_validate_rejects_one_header_mapped_to_two_fields() -> None:
    with pytest.raises(MappingError, match="cannot be mapped to both"):
        mapping.validate_mapping(
            ORDERS, ["A"], {"external_order_id": "A", "order_date": "A"}
        )


# --- map_row ---------------------------------------------------------------


def test_map_row_projects_onto_canonical_names() -> None:
    projected = mapping.map_row(
        {"Order ID": "A-1", "Order Amount": "10.00", "Ignored": "x"},
        {"external_order_id": "Order ID", "order_amount": "Order Amount"},
    )

    assert projected == {"external_order_id": "A-1", "order_amount": "10.00"}


def test_map_row_omits_fields_whose_column_is_absent() -> None:
    projected = mapping.map_row(
        {"Order ID": "A-1"}, {"external_order_id": "Order ID", "order_date": "Order Date"}
    )

    assert projected == {"external_order_id": "A-1"}
