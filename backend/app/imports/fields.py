"""The canonical-field registry.

Every imported value is stored against a *canonical* field name rather than the
partner's own column header, so downstream logic never has to know that
Flipkart calls it ``Order ID`` while a courier calls it ``AWB Reference``.

This module is the single source of truth for:

* which canonical fields exist and how their raw text is interpreted;
* the alternative header spellings ("aliases") that are recognised; and
* which fields each source type must have before an import can be processed.

It deliberately knows nothing about CSV/XLSX parsing, HTTP or the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.models.enums import ImportSourceType

#: How a raw cell is interpreted by :mod:`app.imports.normalizer`.
VALUE_TEXT = "text"
VALUE_DATE = "date"
VALUE_AMOUNT = "amount"

# Collapses any run of non-alphanumeric characters so ``"Order ID"``,
# ``"order_id"`` and ``"ORDER  ID"`` all compare equal.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_header(header: str) -> str:
    """Reduce a header to a comparable form (lower case, single-spaced)."""
    return _NON_ALNUM.sub(" ", header.strip().lower()).strip()


@dataclass(frozen=True)
class CanonicalField:
    """A platform-owned field that imported values are stored against."""

    name: str
    label: str
    kind: str
    aliases: tuple[str, ...]

    @property
    def normalized_aliases(self) -> tuple[str, ...]:
        """The aliases in :func:`normalize_header` form, longest first.

        Longest-first matters for the substring tier of suggestion: a header
        like ``"total shipping charge"`` should claim the more specific
        ``shipping charge`` alias rather than a shorter overlapping one.
        """
        normalised = {normalize_header(alias) for alias in self.aliases}
        normalised.add(normalize_header(self.name))
        return tuple(sorted(normalised, key=lambda item: (-len(item), item)))


CANONICAL_FIELDS: tuple[CanonicalField, ...] = (
    CanonicalField(
        name="external_order_id",
        label="External order ID",
        kind=VALUE_TEXT,
        aliases=(
            "order id",
            "orderid",
            "order no",
            "order number",
            "order code",
            "external order id",
            "marketplace order id",
            "merchant order id",
            "sub order id",
            "suborder id",
            "reference order id",
            "sales order number",
        ),
    ),
    CanonicalField(
        name="order_date",
        label="Order date",
        kind=VALUE_DATE,
        aliases=(
            "order date",
            "orderdate",
            "order date time",
            "purchase date",
            "booking date",
            "order created at",
            "date",
        ),
    ),
    CanonicalField(
        name="customer_name",
        label="Customer name",
        kind=VALUE_TEXT,
        aliases=(
            "customer name",
            "customername",
            "customer full name",
            "buyer name",
            "buyer",
            "customer",
            "ship to name",
            "shipping name",
            "recipient name",
            "consignee name",
        ),
    ),
    CanonicalField(
        name="order_amount",
        label="Order amount",
        kind=VALUE_AMOUNT,
        aliases=(
            "order amount",
            "orderamount",
            "order value",
            "order total",
            "gross amount",
            "item total",
            "invoice amount",
            "grand total",
            "total amount",
            "amount",
        ),
    ),
    CanonicalField(
        name="payment_mode",
        label="Payment mode",
        kind=VALUE_TEXT,
        aliases=(
            "payment mode",
            "paymentmode",
            "pay mode",
            "paymode",
            "payment method",
            "payment type",
            "mode of payment",
            "payment",
        ),
    ),
    CanonicalField(
        name="order_status",
        label="Order status",
        kind=VALUE_TEXT,
        aliases=(
            "order status",
            "orderstatus",
            "order state",
            "fulfilment status",
            "fulfillment status",
            "current status",
            "status",
        ),
    ),
    CanonicalField(
        name="settlement_amount",
        label="Settlement amount",
        kind=VALUE_AMOUNT,
        aliases=(
            "settlement amount",
            "settlementamount",
            "settled amount",
            "net amount",
            "net settlement",
            "net payable",
            "amount settled",
            "amount credited",
            "credit amount",
            "payout amount",
            "remitted amount",
            "remittance amount",
            "final amount",
            "settlement value",
        ),
    ),
    CanonicalField(
        name="transaction_reference",
        label="Transaction reference",
        kind=VALUE_TEXT,
        aliases=(
            "transaction reference",
            "transactionreference",
            "transaction id",
            "transactionid",
            "transaction number",
            "txn id",
            "reference number",
            "reference id",
            "payment reference",
            "bank reference",
            "settlement id",
            "payout id",
            "utr number",
            "utr",
            "reference",
        ),
    ),
    CanonicalField(
        name="courier_name",
        label="Courier name",
        kind=VALUE_TEXT,
        aliases=(
            "courier name",
            "couriername",
            "courier partner",
            "courier",
            "logistics partner",
            "logistics provider",
            "shipping partner",
            "carrier name",
            "carrier",
            "transporter",
        ),
    ),
    CanonicalField(
        name="shipping_charge",
        label="Shipping charge",
        kind=VALUE_AMOUNT,
        aliases=(
            "shipping charge",
            "shippingcharge",
            "shipping charges",
            "shipping fee",
            "shipping amount",
            "delivery charge",
            "delivery charges",
            "freight charge",
            "freight charges",
            "freight amount",
            "forward shipping fee",
            "logistics charge",
            "freight",
        ),
    ),
    CanonicalField(
        name="return_status",
        label="Return status",
        kind=VALUE_TEXT,
        aliases=(
            "return status",
            "returnstatus",
            "return state",
            "return type",
            "return reason",
            "return disposition",
            "return remarks",
            "return request status",
            "rto status",
        ),
    ),
    CanonicalField(
        name="zone",
        label="Delivery zone",
        kind=VALUE_TEXT,
        aliases=(
            "zone",
            "zone code",
            "shipping zone",
            "ship zone",
            "delivery zone",
            "delivery region",
        ),
    ),
    CanonicalField(
        name="weight_grams",
        label="Shipment weight (grams)",
        kind=VALUE_AMOUNT,
        aliases=(
            "weight grams",
            "weight in grams",
            "weight g",
            "charged weight",
            "dead weight",
            "weight",
        ),
    ),
    CanonicalField(
        name="tcs_amount",
        label="TCS",
        kind=VALUE_AMOUNT,
        aliases=(
            "tcs",
            "tcs amount",
            "gst tcs",
            "tax collected at source",
            "tcs deducted",
        ),
    ),
    CanonicalField(
        name="tds_amount",
        label="TDS",
        kind=VALUE_AMOUNT,
        aliases=(
            "tds",
            "tds amount",
            "gst tds",
            "tax deducted at source",
            "tds deducted",
        ),
    ),
)

FIELD_BY_NAME: Mapping[str, CanonicalField] = MappingProxyType(
    {field.name: field for field in CANONICAL_FIELDS}
)

ALL_FIELD_NAMES: tuple[str, ...] = tuple(field.name for field in CANONICAL_FIELDS)


def _build_alias_index() -> Mapping[str, CanonicalField]:
    """Map a normalised alias to the field that owns it.

    Only unambiguous aliases are kept: if two fields claim the same spelling it
    is dropped entirely, so suggestion can never guess between them.
    """
    claims: dict[str, list[CanonicalField]] = {}
    for field in CANONICAL_FIELDS:
        for alias in field.normalized_aliases:
            claims.setdefault(alias, []).append(field)

    return MappingProxyType(
        {alias: owners[0] for alias, owners in claims.items() if len(owners) == 1}
    )


#: Normalised alias -> the single field that owns it.
ALIAS_INDEX: Mapping[str, CanonicalField] = _build_alias_index()

#: Fields that must be present before a source type can be processed.
REQUIRED_FIELDS: Mapping[ImportSourceType, tuple[str, ...]] = MappingProxyType(
    {
        ImportSourceType.ORDERS: ("external_order_id", "order_date", "order_amount"),
        ImportSourceType.SETTLEMENTS: ("transaction_reference", "settlement_amount"),
        ImportSourceType.COD_REMITTANCES: ("transaction_reference", "settlement_amount"),
        ImportSourceType.FREIGHT_INVOICES: ("courier_name", "shipping_charge"),
        ImportSourceType.RETURNS: ("external_order_id", "return_status"),
    }
)

#: Fields that are useful but not essential for each source type.
OPTIONAL_FIELDS: Mapping[ImportSourceType, tuple[str, ...]] = MappingProxyType(
    {
        ImportSourceType.ORDERS: (
            "customer_name",
            "payment_mode",
            "order_status",
            "shipping_charge",
            "courier_name",
            "zone",
            "weight_grams",
        ),
        ImportSourceType.SETTLEMENTS: (
            "external_order_id",
            "order_date",
            "order_status",
            "courier_name",
            "shipping_charge",
            "tcs_amount",
            "tds_amount",
        ),
        ImportSourceType.COD_REMITTANCES: (
            "external_order_id",
            "order_date",
            "courier_name",
            "shipping_charge",
            "tcs_amount",
            "tds_amount",
        ),
        ImportSourceType.FREIGHT_INVOICES: (
            "transaction_reference",
            "order_date",
            "external_order_id",
            "zone",
            "weight_grams",
            "tcs_amount",
            "tds_amount",
        ),
        ImportSourceType.RETURNS: (
            "order_date",
            "customer_name",
            "order_amount",
            "courier_name",
            "shipping_charge",
        ),
    }
)

#: Source types the import API accepts. ``CLAIMS`` exists in the schema for
#: forward compatibility but is intentionally not handled yet.
SUPPORTED_SOURCE_TYPES: tuple[ImportSourceType, ...] = (
    ImportSourceType.ORDERS,
    ImportSourceType.SETTLEMENTS,
    ImportSourceType.COD_REMITTANCES,
    ImportSourceType.FREIGHT_INVOICES,
    ImportSourceType.RETURNS,
)

#: Human labels for the supported source types.
SOURCE_TYPE_LABELS: Mapping[ImportSourceType, str] = MappingProxyType(
    {
        ImportSourceType.ORDERS: "Orders",
        ImportSourceType.SETTLEMENTS: "Marketplace settlements",
        ImportSourceType.COD_REMITTANCES: "COD remittances",
        ImportSourceType.FREIGHT_INVOICES: "Freight invoices",
        ImportSourceType.RETURNS: "Returns",
    }
)


def fields_for_source(source_type: ImportSourceType) -> tuple[CanonicalField, ...]:
    """Return the source's fields, required ones first.

    The order is what the mapping UI renders, so the fields a human has to care
    about most appear at the top.
    """
    required = REQUIRED_FIELDS.get(source_type, ())
    optional = OPTIONAL_FIELDS.get(source_type, ())
    ordered = (*required, *optional, *ALL_FIELD_NAMES)
    seen: dict[str, CanonicalField] = {}
    for name in ordered:
        if name not in seen:
            seen[name] = FIELD_BY_NAME[name]
    return tuple(seen.values())


def required_fields_for_source(source_type: ImportSourceType) -> tuple[str, ...]:
    """Return the canonical fields that must be mapped for ``source_type``."""
    return REQUIRED_FIELDS.get(source_type, ())
