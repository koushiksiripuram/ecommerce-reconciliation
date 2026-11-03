"""Reconciliation result model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import portable_enum
from app.models.enums import ReconciliationStatus
from app.models.order import MONEY

if TYPE_CHECKING:
    from app.models.imports import ImportBatch
    from app.models.order import Order
    from app.models.settlement import SettlementRecord


class ReconciliationResult(Base, TimestampMixin):
    """The outcome of comparing one order against one settlement record.

    Only the *result* is modelled here. The comparison logic that produces
    these rows is intentionally not implemented in this milestone.
    """

    __tablename__ = "reconciliation_results"
    __table_args__ = (
        Index("ix_reconciliation_results_run_status", "import_batch_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    settlement_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("settlement_records.id", ondelete="CASCADE"), nullable=True, index=True
    )
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[ReconciliationStatus] = mapped_column(
        portable_enum(ReconciliationStatus, "reconciliation_status"),
        nullable=False,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'INR'"))

    expected_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    actual_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    difference_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order | None"] = relationship(back_populates="reconciliation_results")
    settlement_record: Mapped["SettlementRecord | None"] = relationship(
        back_populates="reconciliation_results"
    )
    import_batch: Mapped["ImportBatch | None"] = relationship(
        back_populates="reconciliation_results"
    )

    def __repr__(self) -> str:
        return (
            f"<ReconciliationResult id={self.id} status={self.status} "
            f"difference={self.difference_amount}>"
        )
