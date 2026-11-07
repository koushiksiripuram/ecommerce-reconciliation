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
    """Kind of source data contained in an import batch.

    ``CLAIMS`` is declared in the schema for forward compatibility but is not
    accepted by the import API yet.
    """

    ORDERS = "orders"
    SETTLEMENTS = "settlements"
    COD_REMITTANCES = "cod_remittances"
    FREIGHT_INVOICES = "freight_invoices"
    RETURNS = "returns"
    CLAIMS = "claims"


class ImportBatchStatus(str, Enum):
    """Processing state of an import batch.

    ``UPLOADED`` means the file is parsed and a complete mapping is in place, so
    it is ready to process. ``MAPPING_REQUIRED`` means at least one required
    canonical field is still unmapped and a human must intervene.
    """

    UPLOADED = "uploaded"
    MAPPING_REQUIRED = "mapping_required"
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
    """Outcome of comparing an order against its settlement records.

    ``SETTLED``/``SHORT_PAID``/``UNPAID_PAST_DUE``/``PENDING`` describe the
    order's payment state. ``MISSING_IN_ORDERS`` records a received settlement
    line that could not be tied back to any order; those rows are never
    discarded, they are reported so they can be investigated.
    """

    SETTLED = "settled"
    SHORT_PAID = "short_paid"
    UNPAID_PAST_DUE = "unpaid_past_due"
    PENDING = "pending"
    MISSING_IN_ORDERS = "missing_in_orders"


class FreightServiceType(str, Enum):
    """Direction of a shipment leg, used to look up a freight rate."""

    FORWARD = "forward"
    REVERSE = "reverse"


class FreightPaymentType(str, Enum):
    """How the shipment was paid for, used to look up a freight rate."""

    PREPAID = "prepaid"
    COD = "cod"
