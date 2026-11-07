"""Configurable freight rate cards.

Freight is not a fixed number: a courier charges by weight slab, delivery zone,
direction (forward or reverse) and payment type (prepaid or cash on delivery).
A rate card captures one such combination, and the reconciliation engine looks
up the expected freight for a shipment rather than hardcoding any courier's
tariff.

Rate cards are reference data and are populated out of band (a migration, an
admin import or direct SQL); this milestone ships the lookup, not a CRUD API.
"""

from decimal import Decimal

from sqlalchemy import Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import portable_enum
from app.models.enums import FreightPaymentType, FreightServiceType
from app.models.order import MONEY

#: Shipment weight is held in grams so no fractional rounding is needed.
WEIGHT = Numeric(10, 3)


class FreightRateCard(Base, TimestampMixin):
    """The charge for one courier/zone/service/payment weight slab."""

    __tablename__ = "freight_rate_cards"
    __table_args__ = (
        # One rate per slab start keeps lookups unambiguous.
        UniqueConstraint(
            "courier",
            "zone",
            "service_type",
            "payment_type",
            "min_weight_grams",
            name="uq_freight_rate_cards_slab",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    #: Courier as reported on the order/settlement, matched case-insensitively.
    courier: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: Delivery zone, matched case-insensitively.
    zone: Mapped[str] = mapped_column(String(32), nullable=False)

    service_type: Mapped[FreightServiceType] = mapped_column(
        portable_enum(FreightServiceType, "freight_service_type"),
        nullable=False,
        default=FreightServiceType.FORWARD,
        server_default=FreightServiceType.FORWARD.value,
    )
    payment_type: Mapped[FreightPaymentType] = mapped_column(
        portable_enum(FreightPaymentType, "freight_payment_type"),
        nullable=False,
        default=FreightPaymentType.PREPAID,
        server_default=FreightPaymentType.PREPAID.value,
    )

    #: Inclusive lower bound and exclusive upper bound of the slab, in grams.
    min_weight_grams: Mapped[Decimal] = mapped_column(
        WEIGHT, nullable=False, default=Decimal("0"), server_default=text("0")
    )
    max_weight_grams: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)

    rate: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'INR'")
    )

    def __repr__(self) -> str:
        return (
            f"<FreightRateCard id={self.id} courier={self.courier!r} "
            f"zone={self.zone!r} rate={self.rate}>"
        )
