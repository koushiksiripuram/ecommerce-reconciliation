"""Enumerations shared across models.

Every enum is persisted with ``native_enum=False`` so PostgreSQL stores a
``VARCHAR`` with a ``CHECK`` constraint. This keeps migrations portable and
avoids PostgreSQL's native enum type, which is awkward to alter later.
"""

from enum import Enum


class OrderStatus(str, Enum):
    """Lifecycle state of a marketplace order."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class ImportSourceType(str, Enum):
    """Kind of source data contained in an import batch."""

    ORDERS = "orders"
    SETTLEMENTS = "settlements"
    RETURNS = "returns"
    CLAIMS = "claims"


class ImportBatchStatus(str, Enum):
    """Processing state of an import batch."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SettlementTransactionType(str, Enum):
    """Nature of a settlement line item."""

    SALE = "sale"
    REFUND = "refund"
    CHARGEBACK = "chargeback"
    FEE = "fee"
    ADJUSTMENT = "adjustment"


class ReconciliationStatus(str, Enum):
    """Outcome of comparing an order against its settlement records."""

    MATCHED = "matched"
    AMOUNT_MISMATCH = "amount_mismatch"
    MISSING_IN_SETTLEMENT = "missing_in_settlement"
    MISSING_IN_ORDERS = "missing_in_orders"
    PARTIAL = "partial"
    UNMATCHED = "unmatched"
