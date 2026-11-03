"""Order model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import portable_enum
from app.models.enums import OrderStatus

if TYPE_CHECKING:
    from app.models.reconciliation import ReconciliationResult
    from app.models.settlement import SettlementRecord

# Monetary columns share one precision/scale across the schema.
MONEY = Numeric(14, 2)


class Order(Base, TimestampMixin):
    """An order placed on a marketplace, as reported by that marketplace.

    ``marketplace`` + ``external_order_id`` identify the order at the source;
    ``id`` is the internal surrogate key.
    """

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("marketplace", "external_order_id", name="uq_orders_marketplace_external_order_id"),
        Index("ix_orders_marketplace_order_date", "marketplace", "order_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    external_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)

    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        portable_enum(OrderStatus, "order_status"),
        nullable=False,
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'INR'"))

    gross_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    shipping_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    net_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default=text("0")
    )

    # Mirrors the ON DELETE SET NULL rule on settlement_records.order_id: the
    # settlement survives but loses its link to this order.
    settlement_records: Mapped[list["SettlementRecord"]] = relationship(
        back_populates="order",
    )
    # Mirrors ON DELETE CASCADE: a result is meaningless without its order.
    reconciliation_results: Mapped[list["ReconciliationResult"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} marketplace={self.marketplace!r} "
            f"external_order_id={self.external_order_id!r}>"
        )
