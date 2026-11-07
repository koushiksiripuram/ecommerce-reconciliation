"""Freight rate-card lookup.

Given the attributes of a shipment (courier, zone, direction, payment type and
weight) this module returns the freight a configured rate card says should have
been charged. It is the only place that knows how a slab is selected, so the
reconciliation engine never embeds a courier's tariff.

The lookup is deliberately conservative: when any attribute is missing, or no
card matches, it returns ``None`` and no freight expectation is produced. A
missing rate card is a configuration gap, not an overcharge.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FreightPaymentType, FreightRateCard, FreightServiceType


def resolve_freight(
    db: Session,
    *,
    courier: str | None,
    zone: str | None,
    service_type: FreightServiceType,
    payment_type: FreightPaymentType,
    weight_grams: Decimal | None,
) -> Decimal | None:
    """Return the configured freight rate for a shipment, or ``None``.

    ``weight_grams`` selects the slab whose inclusive lower and exclusive upper
    bound contain the weight; courier and zone are compared case-insensitively
    because the same partner spells them inconsistently across files.
    """
    if weight_grams is None or not courier or not zone:
        return None

    statement = (
        select(FreightRateCard.rate)
        .where(
            func.lower(FreightRateCard.courier) == courier.strip().lower(),
            func.lower(FreightRateCard.zone) == zone.strip().lower(),
            FreightRateCard.service_type == service_type,
            FreightRateCard.payment_type == payment_type,
            FreightRateCard.min_weight_grams <= weight_grams,
            FreightRateCard.max_weight_grams > weight_grams,
        )
        .order_by(FreightRateCard.min_weight_grams.desc())
        .limit(1)
    )
    return db.scalar(statement)
