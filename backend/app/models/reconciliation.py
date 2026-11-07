"""Reconciliation result and run models."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
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
    from app.models.user import User


class ReconciliationRun(Base, TimestampMixin):
    """An immutable snapshot of one reconciliation execution.

    Every run recomputes the whole result set from the imported data, but instead
    of deleting the previous results it supersedes them: the rows stay in the
    database tagged with the run that produced them, so a finance team can still
    see what a past run concluded. Exactly one run is flagged ``is_current`` — the
    latest one — and that is what the default list/detail/summary views read.

    ``source_watermark`` records the highest completed import batch id that fed
    the run, which is a cheap way to tell whether a later run consumed new data.
    The summary counts are stored too, so a run can be reported without
    recomputing it.
    """

    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    triggered_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    #: Highest completed import batch id that contributed to this run.
    source_watermark: Mapped[int | None] = mapped_column(nullable=True)

    orders_reconciled: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    settlements_matched: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    unmatched_settlements: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    results_created: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    by_status: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)

    #: True for the most recent run only; the default views read this one.
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )

    triggered_by: Mapped["User | None"] = relationship()
    results: Mapped[list["ReconciliationResult"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ReconciliationRun id={self.id} results={self.results_created} "
            f"current={self.is_current}>"
        )


class ReconciliationResult(Base, TimestampMixin):
    """The outcome of comparing one order against its settlement records.

    A row is one reconciliation *line*: for a normal order it links the order to
    the settlement records that paid it; for a settlement line that could not be
    tied to any order it links only the settlement record, so unmatched money is
    never silently dropped.

    ``expected_amount`` is what should have been received, ``actual_amount`` is
    what was received, and ``difference_amount`` is the signed gap between them.
    Tax withheld at source is tracked separately in ``tcs_amount``/``tds_amount``
    so it is never reported as revenue leakage. The structured list of detected
    problems (freight overcharge, duplicate settlement, missing reference, ...)
    is kept in ``issues`` and points back at the settlement records that are the
    supporting evidence.
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
    #: The run that produced this line. ``NULL`` for rows created before run
    #: history existed; new runs always set it.
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )

    #: True while this line belongs to the latest run. A new run flips the
    #: previous lines to ``False`` (superseded) instead of deleting them, so the
    #: history is preserved and the default views can simply read the current set.
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
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

    #: Freight the rate card says should have been charged, and the freight that
    #: was actually charged. Kept on the result so an overcharge can be proven
    #: without re-running the rate card lookup.
    expected_freight_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    actual_freight_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )

    #: Tax collected/deducted at source. Recorded apart from the amount gap so
    #: legitimate withholding is never counted as revenue leakage.
    tcs_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    tds_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )

    #: Structured problems found for this line, e.g.
    #: ``{"code": "freight_overcharged", "message": "...", "amount": "125.00"}``.
    #: Each entry may carry the id of the settlement record that evidences it.
    issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order | None"] = relationship(back_populates="reconciliation_results")
    settlement_record: Mapped["SettlementRecord | None"] = relationship(
        back_populates="reconciliation_results"
    )
    import_batch: Mapped["ImportBatch | None"] = relationship(
        back_populates="reconciliation_results"
    )
    run: Mapped["ReconciliationRun | None"] = relationship(back_populates="results")

    def __repr__(self) -> str:
        return (
            f"<ReconciliationResult id={self.id} status={self.status} "
            f"difference={self.difference_amount}>"
        )
