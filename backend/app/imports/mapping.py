"""Suggestion and validation of the header-to-canonical-field mapping.

This module never touches file bytes: it receives a list of header names and
returns a proposed mapping. Keeping it separate is what allows the same logic
to serve the upload flow, the saved-mapping reuse and the manual-correction
endpoint.

Every suggestion is *deterministic* — derived from exact header equality and a
curated alias list — so nothing is ever guessed probabilistically. A batch is
only considered ready to process when every required canonical field has been
resolved; anything unresolved is left for a human to correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.imports.errors import MappingError
from app.imports.fields import (
    ALIAS_INDEX,
    FIELD_BY_NAME,
    REQUIRED_FIELDS,
    CanonicalField,
    fields_for_source,
    normalize_header,
)
from app.models.enums import ImportSourceType

#: Confidence labels reported back to the UI, best first.
CONFIDENCE_SAVED = "saved"
CONFIDENCE_EXACT = "exact"
CONFIDENCE_ALIAS = "alias"
CONFIDENCE_CONTAINS = "contains"
CONFIDENCE_MANUAL = "manual"


@dataclass(frozen=True)
class FieldSuggestion:
    """What a single canonical field was matched to (if anything)."""

    field: str
    header: str | None
    confidence: str | None
    required: bool


@dataclass(frozen=True)
class MappingSuggestion:
    """The full proposal for one set of headers."""

    mapping: dict[str, str]
    fields: tuple[FieldSuggestion, ...]
    unmapped_headers: tuple[str, ...]
    missing_required: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        """True when every required field has been resolved."""
        return not self.missing_required

    def confidence_for(self, field_name: str) -> str | None:
        """The confidence recorded for ``field_name``, if it was suggested."""
        for suggestion in self.fields:
            if suggestion.field == field_name:
                return suggestion.confidence
        return None


def suggest_mapping(
    source_type: ImportSourceType,
    headers: list[str],
    saved: Mapping[str, str] | None = None,
) -> MappingSuggestion:
    """Propose a mapping for ``headers``.

    Resolution order, strongest first:

    1. an approved mapping previously saved for this source type and partner;
    2. a header that equals the canonical field name;
    3. a header that equals one of the field's aliases;
    4. a header that *contains* an alias as whole words.

    Tiers 1-3 are exact, so they are trusted. Tier 4 is still deterministic but
    looser, so it is reported with a lower confidence and never on its own
    justifies treating an ambiguous header as settled.
    """
    field_definitions = fields_for_source(source_type)
    required = set(REQUIRED_FIELDS.get(source_type, ()))

    headers_by_normalized: dict[str, str] = {}
    for header in headers:
        normalized = normalize_header(header)
        if normalized and normalized not in headers_by_normalized:
            headers_by_normalized[normalized] = header

    resolved: dict[str, tuple[str, str]] = {}
    used_headers: set[str] = set()

    def claim(field: CanonicalField, header: str, confidence: str) -> bool:
        if field.name in resolved or header in used_headers:
            return False
        resolved[field.name] = (header, confidence)
        used_headers.add(header)
        return True

    # Tier 1: a previously approved mapping always wins.
    if saved:
        for field in field_definitions:
            header = saved.get(field.name)
            if header and header in headers:
                claim(field, header, CONFIDENCE_SAVED)

    # Tier 2: the header already is the canonical name.
    for field in field_definitions:
        header = headers_by_normalized.get(normalize_header(field.name))
        if header is not None:
            claim(field, header, CONFIDENCE_EXACT)

    # Tier 3: the header equals a known alias.
    for field in field_definitions:
        for alias in field.normalized_aliases:
            owner = ALIAS_INDEX.get(alias)
            header = headers_by_normalized.get(alias)
            if header is not None and owner is field:
                if claim(field, header, CONFIDENCE_ALIAS):
                    break

    # Tier 4: the header contains an alias as a whole word.
    for field in field_definitions:
        if field.name in resolved:
            continue
        for header in headers:
            if header in used_headers:
                continue
            if _contains_alias(field, normalize_header(header)):
                if claim(field, header, CONFIDENCE_CONTAINS):
                    break

    fields = tuple(
        FieldSuggestion(
            field=field.name,
            header=resolved.get(field.name, (None, None))[0],
            confidence=resolved.get(field.name, (None, None))[1],
            required=field.name in required,
        )
        for field in field_definitions
    )

    mapping = {field_name: header for field_name, (header, _) in resolved.items()}
    unmapped_headers = tuple(header for header in headers if header not in used_headers)
    missing_required = tuple(name for name in required if name not in resolved)

    return MappingSuggestion(
        mapping=mapping,
        fields=fields,
        unmapped_headers=unmapped_headers,
        missing_required=missing_required,
    )


def _contains_alias(field: CanonicalField, normalized_header: str) -> bool:
    """True when ``normalized_header`` contains one of the field's aliases.

    Matching happens on whole tokens so ``"order dated"`` does not match the
    ``order date`` alias.
    """
    header_tokens = set(normalized_header.split())
    if not header_tokens:
        return False

    return any(set(alias.split()) <= header_tokens for alias in field.normalized_aliases)


@dataclass(frozen=True)
class ValidatedMapping:
    """A mapping that has been checked against a concrete set of headers."""

    mapping: dict[str, str]
    missing_required: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return not self.missing_required


def validate_mapping(
    source_type: ImportSourceType,
    headers: list[str],
    mapping: Mapping[str, str | None] | None,
    *,
    require_complete: bool = False,
) -> ValidatedMapping:
    """Check a caller-supplied mapping against the file's real headers.

    Raises :class:`MappingError` for structural problems (unknown field, header
    that is not in the file, one header used twice). Missing required fields are
    reported rather than raised, unless ``require_complete`` is set.
    """
    cleaned: dict[str, str] = {}
    for field_name, header in (mapping or {}).items():
        if header is None or not str(header).strip():
            continue

        if field_name not in FIELD_BY_NAME:
            raise MappingError(f"Unknown canonical field {field_name!r}.")

        header = str(header).strip()
        if header not in headers:
            raise MappingError(
                f"Column {header!r} mapped to {field_name!r} is not present in the file."
            )

        already = next((name for name, value in cleaned.items() if value == header), None)
        if already is not None:
            raise MappingError(
                f"Column {header!r} cannot be mapped to both {already!r} and {field_name!r}."
            )

        cleaned[field_name] = header

    missing_required = tuple(
        name for name in REQUIRED_FIELDS.get(source_type, ()) if name not in cleaned
    )
    if require_complete and missing_required:
        raise MappingError(
            "The mapping is incomplete; still missing: " + ", ".join(missing_required) + "."
        )

    return ValidatedMapping(mapping=cleaned, missing_required=missing_required)


def map_row(raw_row: Mapping[str, str], mapping: Mapping[str, str]) -> dict[str, str]:
    """Project a header-keyed raw row onto canonical field names.

    Values are passed through untouched; interpreting them is the normalizer's
    job. Fields whose column was not mapped are simply absent.
    """
    return {
        field_name: raw_row.get(header, "")
        for field_name, header in mapping.items()
        if header in raw_row
    }
