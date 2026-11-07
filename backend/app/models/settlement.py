"""Settlement record model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import portable_enum
from app.models.enums import SettlementTransactionType
from app.models.order import MONEY

if TYPE_CHECKING:
    from app.models.imports import ImportBatch, RawImportedRecord
    from app.models.order import Order
    from app.models.reconciliation import ReconciliationResult


class SettlementRecord(Base, TimestampMixin):
    """A payout line reported by a marketplace.

    ``order_id`` is populated only once the record has been linked to an order;
    unmatched settlement lines stay with ``order_id = NULL`` so nothing is lost.
    """

    __tablename__ = "settlement_records"
    __table_args__ = (
        UniqueConstraint(
            "marketplace", "external_reference", name="uq_settlement_records_marketplace_external"
        ),
        Index("ix_settlement_records_marketplace_settlement_date", "marketplace", "settlement_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    #: The marketplace order id this line settles, when the file carries one.
    #: It is the join key used to match a settlement back to an order; unlike
    #: ``external_reference`` it does not have to be unique.
    order_reference: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )

    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raw_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_imported_records.id", ondelete="SET NULL"), nullable=True, index=True
    )

    transaction_type: Mapped[SettlementTransactionType] = mapped_column(
        portable_enum(SettlementTransactionType, "settlement_transaction_type"),
        nullable=False,
    )
    settlement_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'INR'"))

    gross_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    fee_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    net_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )

    order: Mapped["Order | None"] = relationship(back_populates="settlement_records")
    import_batch: Mapped["ImportBatch | None"] = relationship(back_populates="settlement_records")
    raw_record: Mapped["RawImportedRecord | None"] = relationship(
        back_populates="settlement_records"
    )
    # Mirrors ON DELETE CASCADE: a result is meaningless without its settlement.
    reconciliation_results: Mapped[list["ReconciliationResult"]] = relationship(
        back_populates="settlement_record",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<SettlementRecord id={self.id} marketplace={self.marketplace!r} "
            f"external_reference={self.external_reference!r}>"
        )
