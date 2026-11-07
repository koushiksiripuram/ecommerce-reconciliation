"""Row-level interpretation and validation.

Given a row that has already been projected onto canonical field names, this
module decides what each value *means* (an amount, a date, plain text) and
reports anything that could not be interpreted.

Nothing here mutates the raw row: an amount becomes a decimal string, a date an
ISO date, text is trimmed. Values that cannot be interpreted are recorded as an
issue on the row instead of being coerced or discarded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.imports.fields import (
    FIELD_BY_NAME,
    REQUIRED_FIELDS,
    VALUE_AMOUNT,
    VALUE_DATE,
)
from app.models.enums import ImportSourceType

#: Validation error codes. Stable identifiers the UI can switch on.
CODE_REQUIRED = "required"
CODE_INVALID_AMOUNT = "invalid_amount"
CODE_INVALID_DATE = "invalid_date"

#: Length of ``raw_imported_records.external_reference``.
EXTERNAL_REFERENCE_MAX_LENGTH = 128

#: Fields consulted, in order, when deriving the row's external reference.
_REFERENCE_FIELDS = ("external_order_id", "transaction_reference")

# Everything that is not a digit or a numeric separator is dropped before an
# amount is parsed, so "₹1,234.56", "INR 1234.56" and "Rs. 1,234.56" agree.
_NON_NUMERIC = re.compile(r"[^0-9.,+\-]")

#: Day-first formats are listed before month-first ones, so an ambiguous value
#: like ``01/02/2026`` is read as 1 February. This is documented behaviour
#: rather than a silent guess.
_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%d-%m-%y",
    "%d/%m/%y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%d-%B-%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%m/%d/%Y",
    "%m-%d-%Y",
)


@dataclass(frozen=True)
class ValidationIssue:
    """One problem found in one row, addressed to one field."""

    field: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        """Plain form suitable for storing as JSON."""
        return {"field": self.field, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class NormalizedRow:
    """The canonical projection of a row plus whatever went wrong."""

    normalized: dict[str, Any]
    issues: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        """A row is rejected when any field could not be interpreted."""
        return not self.issues


def normalize_row(
    mapped: Mapping[str, str],
    source_type: ImportSourceType,
) -> NormalizedRow:
    """Interpret and validate one already-mapped row."""
    normalized: dict[str, Any] = {}
    issues: list[ValidationIssue] = []

    for field_name, raw_value in mapped.items():
        field = FIELD_BY_NAME[field_name]
        value = (raw_value if isinstance(raw_value, str) else str(raw_value)).strip()

        if not value:
            normalized[field_name] = None
            continue

        if field.kind == VALUE_AMOUNT:
            amount = parse_amount(value)
            if amount is None:
                normalized[field_name] = None
                issues.append(
                    ValidationIssue(
                        field=field_name,
                        code=CODE_INVALID_AMOUNT,
                        message=f"{field.label}: {value!r} is not a valid amount.",
                    )
                )
            else:
                normalized[field_name] = format(amount, "f")
        elif field.kind == VALUE_DATE:
            parsed = parse_date(value)
            if parsed is None:
                normalized[field_name] = None
                issues.append(
                    ValidationIssue(
                        field=field_name,
                        code=CODE_INVALID_DATE,
                        message=f"{field.label}: {value!r} is not a recognised date.",
                    )
                )
            else:
                normalized[field_name] = parsed.isoformat()
        else:
            normalized[field_name] = value

    # A required column can be present but empty. Rows that already failed
    # interpretation are not reported twice.
    for name in REQUIRED_FIELDS.get(source_type, ()):
        if name not in mapped or normalized.get(name) is not None:
            continue
        if any(issue.field == name for issue in issues):
            continue
        issues.append(
            ValidationIssue(
                field=name,
                code=CODE_REQUIRED,
                message=f"{FIELD_BY_NAME[name].label} is required but empty.",
            )
        )

    return NormalizedRow(normalized=normalized, issues=tuple(issues))


def parse_amount(value: str) -> Decimal | None:
    """Parse a monetary string into an exact :class:`Decimal`.

    Handles thousands separators and both ``1,234.56`` and ``1.234,56``
    conventions, currency symbols, a leading or trailing sign and accounting
    parentheses. Returns ``None`` when the text is not a usable number.
    """
    text = value.strip()
    if not text:
        return None

    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").strip()
    text = _NON_NUMERIC.sub("", text)

    if text.startswith("-") or text.endswith("-"):
        negative = True
    text = text.strip("+-")

    if not text or not any(character.isdigit() for character in text):
        return None

    text = _resolve_separators(text)
    if not text:
        return None

    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None

    if not amount.is_finite():
        return None

    return -amount if negative else amount


def _resolve_separators(text: str) -> str:
    """Reduce a numeric string to plain ``1234.56`` form."""
    last_dot = text.rfind(".")
    last_comma = text.rfind(",")

    if last_dot != -1 and last_comma != -1:
        # Whichever separator comes last is the decimal one.
        if last_dot > last_comma:
            return text.replace(",", "")
        return text.replace(".", "").replace(",", ".")

    if last_comma != -1:
        return _collapse_repeated_separator(text, ",")

    if last_dot != -1:
        return _collapse_repeated_separator(text, ".")

    return text


def _collapse_repeated_separator(text: str, separator: str) -> str:
    """Decide whether a repeated separator means grouping or decimals.

    Money is written with at most two decimal places, and a grouping separator
    is always followed by exactly three digits, so ``1,234`` and ``12.345.678``
    are digit groups while ``1234,56`` and ``0,5`` are decimals.
    """
    parts = text.split(separator)
    looks_grouped = len(parts) > 2 or (
        len(parts) == 2 and len(parts[1]) == 3 and 0 < len(parts[0]) <= 3
    )
    if looks_grouped:
        return text.replace(separator, "")
    return text.replace(separator, ".")


def parse_date(value: str) -> date | None:
    """Parse an ISO 8601 or common regional date string.

    Returns ``None`` when the text is not a usable date.
    """
    text = value.strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass

    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue

    return None


def external_reference(normalized: Mapping[str, Any]) -> str | None:
    """Pick the value used to link a raw row back to its business document."""
    for name in _REFERENCE_FIELDS:
        value = normalized.get(name)
        if value:
            return str(value)[:EXTERNAL_REFERENCE_MAX_LENGTH]
    return None
