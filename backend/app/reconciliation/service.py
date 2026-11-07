"""Reconciliation orchestration.

This is the only module in :mod:`app.reconciliation` that touches the database.
It owns the whole pipeline:

1. **Project** the imported rows onto :class:`~app.models.Order` and
   :class:`~app.models.SettlementRecord` (upserted by their natural keys, so a
   re-run never duplicates them).
2. **Link** each settlement to the order it settles (by order reference).
3. **Compare** expected against received amounts using exact decimals.
4. **Record** one :class:`~app.models.ReconciliationResult` per order, plus one
   per settlement that could not be tied to an order, so no received money is
   ever discarded.

A run is a full recompute, but a non-destructive one: the previous results are
kept and marked superseded, and the new rows are tagged with the run that
produced them. Because results are derived purely from the projected orders and
settlements, the *current* set is identical between two runs over unchanged data
(idempotent), while every past run's snapshot stays queryable for audit.

Assumptions (documented rather than invented per partner):

* An order's ``net_amount`` is the amount the marketplace is expected to pay.
* A settlement's ``net_amount`` is the amount actually received.
* ``TCS``/``TDS`` are withheld at source and are reported separately; they are
  never counted as revenue leakage, and they are removed from the amount gap
  before the payment state is decided.
* ``shipping_charge`` on a settlement line is the freight actually charged by
  the partner; the expected freight comes from the configured rate cards.
* ``unpaid_past_due`` uses a configurable number of days after the order date.
* A settlement line is identified by ``marketplace`` + ``transaction_reference``
  (falling back to the order reference, then to a synthetic per-row key). The
  same line seen twice in the imported data is a duplicate: it is flagged and
  counted once rather than treated as a second payment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import (
    FreightPaymentType,
    FreightServiceType,
    ImportBatch,
    ImportBatchStatus,
    ImportSourceType,
    Order,
    OrderStatus,
    RawImportedRecord,
    ReconciliationResult,
    ReconciliationRun,
    ReconciliationStatus,
    SettlementRecord,
    SettlementTransactionType,
)
from app.reconciliation.freight import resolve_freight

#: Money is always exact and always two decimals.
CENTS = Decimal("0.01")
ZERO = Decimal("0.00")

ORDER_SOURCE_TYPES: tuple[ImportSourceType, ...] = (ImportSourceType.ORDERS,)
SETTLEMENT_SOURCE_TYPES: tuple[ImportSourceType, ...] = (
    ImportSourceType.SETTLEMENTS,
    ImportSourceType.COD_REMITTANCES,
)

#: Stable issue codes the API and UI can switch on.
ISSUE_FREIGHT_OVERCHARGED = "freight_overcharged"
ISSUE_DUPLICATE_SETTLEMENT = "duplicate_settlement"
ISSUE_MISSING_REFERENCE = "missing_reference"
ISSUE_ORDER_NOT_FOUND = "order_not_found"
ISSUE_RETURN_NOT_RECEIVED = "return_not_received"
ISSUE_OVERPAID = "overpaid"

#: Order-status text is matched by substring; the first hit wins.
_STATUS_HINTS: tuple[tuple[str, OrderStatus], ...] = (
    ("cancel", OrderStatus.CANCELLED),
    ("return", OrderStatus.RETURNED),
    ("rto", OrderStatus.RETURNED),
    ("deliver", OrderStatus.DELIVERED),
    ("ship", OrderStatus.SHIPPED),
    ("confirm", OrderStatus.CONFIRMED),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """Return a timezone-aware datetime (SQLite hands back naive ones)."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _dec(value: Any) -> Decimal:
    """Parse a stored value into an exact two-decimal amount."""
    if value is None:
        return ZERO
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return ZERO
    if not parsed.is_finite():
        return ZERO
    return parsed.quantize(CENTS)


def _weight(value: Any) -> Decimal | None:
    """Parse a shipment weight in grams; kept at full precision (not money)."""
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return _aware(datetime.fromisoformat(text))
    except ValueError:
        return None


def _order_status(value: Any) -> OrderStatus:
    text = _text(value)
    if text:
        lowered = text.lower()
        for token, status in _STATUS_HINTS:
            if token in lowered:
                return status
    return OrderStatus.PENDING


def _payment_type(value: Any) -> FreightPaymentType:
    text = _text(value)
    if text:
        lowered = text.lower()
        if "cod" in lowered or "cash on delivery" in lowered:
            return FreightPaymentType.COD
    return FreightPaymentType.PREPAID


def _service_type(status: OrderStatus, return_status: Any) -> FreightServiceType:
    if status is OrderStatus.RETURNED or _text(return_status):
        return FreightServiceType.REVERSE
    return FreightServiceType.FORWARD


@dataclass
class _OrderAttributes:
    """Freight-relevant attributes gleaned from an order's source row."""

    courier: str | None = None
    zone: str | None = None
    weight_grams: Decimal | None = None
    payment_type: FreightPaymentType = FreightPaymentType.PREPAID
    service_type: FreightServiceType = FreightServiceType.FORWARD
    is_returned: bool = False


@dataclass
class _SettlementExtra:
    """Settlement detail that has no column of its own."""

    tcs: Decimal = ZERO
    tds: Decimal = ZERO
    freight: Decimal = ZERO
    order_reference: str | None = None


@dataclass
class RunSummary:
    """What one reconciliation run produced, plus the run's own identity."""

    run_id: int
    started_at: datetime
    finished_at: datetime
    source_watermark: int | None
    triggered_by_user_id: int | None
    orders_reconciled: int
    settlements_matched: int
    unmatched_settlements: int
    results_created: int
    by_status: dict[str, int] = field(default_factory=dict)


# --- Projection ------------------------------------------------------------


def _completed_batches(
    db: Session, source_types: tuple[ImportSourceType, ...]
) -> list[ImportBatch]:
    return list(
        db.scalars(
            select(ImportBatch).where(
                ImportBatch.status == ImportBatchStatus.COMPLETED,
                ImportBatch.source_type.in_(source_types),
            )
        ).all()
    )


def _valid_records(db: Session, batch_ids: list[int]) -> list[RawImportedRecord]:
    if not batch_ids:
        return []
    return list(
        db.scalars(
            select(RawImportedRecord)
            .where(
                RawImportedRecord.import_batch_id.in_(batch_ids),
                RawImportedRecord.is_valid.is_(True),
            )
            .order_by(RawImportedRecord.import_batch_id, RawImportedRecord.row_number)
        ).all()
    )


def _project_orders(db: Session) -> dict[tuple[str, str], _OrderAttributes]:
    """Upsert an :class:`Order` per imported order row; return freight attributes."""
    batches = _completed_batches(db, ORDER_SOURCE_TYPES)
    batch_by_id = {batch.id: batch for batch in batches}
    attributes: dict[tuple[str, str], _OrderAttributes] = {}
    if not batch_by_id:
        return attributes

    existing = {
        (order.marketplace, order.external_order_id): order
        for order in db.scalars(select(Order)).all()
    }

    for record in _valid_records(db, list(batch_by_id)):
        marketplace = batch_by_id[record.import_batch_id].marketplace
        if not marketplace:
            continue

        data = record.normalized_data or {}
        external_order_id = _text(data.get("external_order_id"))
        if not external_order_id:
            continue

        amount = _dec(data.get("order_amount"))
        shipping = _dec(data.get("shipping_charge"))
        status = _order_status(data.get("order_status"))
        order_date = _parse_datetime(data.get("order_date"))
        key = (marketplace, external_order_id)

        order = existing.get(key)
        if order is None:
            order = Order(
                marketplace=marketplace,
                external_order_id=external_order_id,
                order_date=order_date or _now(),
                status=status,
                gross_amount=amount,
                net_amount=amount,
                shipping_amount=shipping,
            )
            db.add(order)
            existing[key] = order
        else:
            order.order_date = order_date or order.order_date
            order.status = status
            order.gross_amount = amount
            order.net_amount = amount
            order.shipping_amount = shipping

        attributes[key] = _OrderAttributes(
            courier=_text(data.get("courier_name")),
            zone=_text(data.get("zone")),
            weight_grams=_weight(data.get("weight_grams")),
            payment_type=_payment_type(data.get("payment_mode")),
            service_type=_service_type(status, data.get("return_status")),
            is_returned=status is OrderStatus.RETURNED,
        )

    return attributes


def _project_settlements(
    db: Session,
) -> tuple[dict[tuple[str, str], _SettlementExtra], dict[tuple[str, str], list[int]]]:
    """Upsert a :class:`SettlementRecord` per imported payout row.

    Returns the detail that has no column of its own, keyed by the settlement's
    natural key, plus the duplicate keys seen: a duplicate is the *same* payout
    line (same marketplace + reference) produced by more than one source row in
    this pass. A line that merely already exists from a previous run is not a
    duplicate — it is updated in place, which is what keeps a re-run idempotent.
    """
    batches = _completed_batches(db, SETTLEMENT_SOURCE_TYPES)
    batch_by_id = {batch.id: batch for batch in batches}
    extras: dict[tuple[str, str], _SettlementExtra] = {}
    duplicates: dict[tuple[str, str], list[int]] = {}
    if not batch_by_id:
        return extras, duplicates

    existing = {
        (record.marketplace, record.external_reference): record
        for record in db.scalars(select(SettlementRecord)).all()
    }

    #: Natural key -> the id of the first source row that produced it.
    seen: dict[tuple[str, str], int] = {}

    for record in _valid_records(db, list(batch_by_id)):
        marketplace = batch_by_id[record.import_batch_id].marketplace
        if not marketplace:
            continue

        data = record.normalized_data or {}
        order_reference = _text(data.get("external_order_id"))
        transaction_reference = _text(data.get("transaction_reference"))
        external_reference = (
            transaction_reference
            or order_reference
            or f"AUTO-{record.import_batch_id}-{record.row_number}"
        )
        key = (marketplace, external_reference)

        if key in seen:
            # The same payout line arriving twice is flagged, not double counted.
            duplicates.setdefault(key, [seen[key]]).append(record.id)
            continue
        seen[key] = record.id

        amount = _dec(data.get("settlement_amount"))
        gross = _dec(data.get("order_amount"))
        freight = _dec(data.get("shipping_charge"))
        tcs = _dec(data.get("tcs_amount"))
        tds = _dec(data.get("tds_amount"))
        settlement_date = (
            _parse_datetime(data.get("order_date"))
            or _aware(record.created_at)
            or _now()
        )

        extras[key] = _SettlementExtra(
            tcs=tcs, tds=tds, freight=freight, order_reference=order_reference
        )

        settlement = existing.get(key)
        if settlement is None:
            settlement = SettlementRecord(
                marketplace=marketplace,
                external_reference=external_reference,
                transaction_type=SettlementTransactionType.SALE,
                settlement_date=settlement_date,
                currency="INR",
            )
            db.add(settlement)
            existing[key] = settlement

        settlement.order_reference = order_reference
        settlement.gross_amount = gross if gross else amount
        settlement.fee_amount = freight
        settlement.tax_amount = (tcs + tds).quantize(CENTS)
        settlement.net_amount = amount
        settlement.settlement_date = settlement_date
        settlement.import_batch_id = record.import_batch_id
        settlement.raw_record_id = record.id

    return extras, duplicates


def _link_settlements(db: Session, orders: list[Order]) -> None:
    """Point every settlement at the order it settles, or clear the link."""
    by_reference = {(order.marketplace, order.external_order_id): order for order in orders}

    for settlement in db.scalars(select(SettlementRecord)).all():
        reference = settlement.order_reference or settlement.external_reference
        order = by_reference.get((settlement.marketplace, reference))
        expected_order_id = order.id if order is not None else None
        if settlement.order_id != expected_order_id:
            settlement.order_id = expected_order_id


# --- Comparison ------------------------------------------------------------


def _is_past_due(order: Order, now: datetime, days: int) -> bool:
    order_date = _aware(order.order_date)
    if order_date is None:
        return False
    return order_date + timedelta(days=days) < now


def _sum(values: Any) -> Decimal:
    total = ZERO
    for value in values:
        total += value
    return total.quantize(CENTS)


def _build_order_result(
    db: Session,
    order: Order,
    attributes: _OrderAttributes | None,
    linked: list[SettlementRecord],
    extras: dict[tuple[str, str], _SettlementExtra],
    duplicates: dict[tuple[str, str], list[int]],
    now: datetime,
    run_id: int,
) -> ReconciliationResult:
    settings = get_settings()
    tolerance = Decimal(settings.reconciliation_amount_tolerance)

    expected = _dec(order.net_amount)
    actual = _sum(_dec(settlement.net_amount) for settlement in linked)

    linked_extras = [
        extras.get(
            (settlement.marketplace, settlement.external_reference),
            _SettlementExtra(),
        )
        for settlement in linked
    ]
    tcs = _sum(extra.tcs for extra in linked_extras)
    tds = _sum(extra.tds for extra in linked_extras)
    actual_freight = _sum(extra.freight for extra in linked_extras)

    expected_freight = ZERO
    if attributes is not None:
        rate = resolve_freight(
            db,
            courier=attributes.courier,
            zone=attributes.zone,
            service_type=attributes.service_type,
            payment_type=attributes.payment_type,
            weight_grams=attributes.weight_grams,
        )
        if rate is not None:
            expected_freight = _dec(rate)

    difference = (expected - actual).quantize(CENTS)
    # Statutory withholding (TCS/TDS) legitimately reduces the payout, so it is
    # removed from the gap before the payment state is decided. It is reported
    # separately and is never treated as revenue leakage.
    withheld = (tcs + tds).quantize(CENTS)
    effective_gap = (difference - withheld).quantize(CENTS)

    issues: list[dict[str, Any]] = []

    overcharge = (actual_freight - expected_freight).quantize(CENTS)
    if expected_freight > ZERO and overcharge > Decimal(settings.freight_overcharge_tolerance):
        issues.append(
            {
                "code": ISSUE_FREIGHT_OVERCHARGED,
                "message": (
                    f"Freight charged {actual_freight} exceeds the rate card "
                    f"{expected_freight} by {overcharge}."
                ),
                "amount": str(overcharge),
                "settlement_record_ids": [settlement.id for settlement in linked],
            }
        )

    duplicate_references = [
        settlement.external_reference
        for settlement in linked
        if (settlement.marketplace, settlement.external_reference) in duplicates
    ]
    if duplicate_references:
        issues.append(
            {
                "code": ISSUE_DUPLICATE_SETTLEMENT,
                "message": (
                    "The same settlement line was received more than once: "
                    + ", ".join(sorted(set(duplicate_references)))
                    + "."
                ),
                "references": sorted(set(duplicate_references)),
            }
        )

    if not linked:
        if attributes is not None and attributes.is_returned:
            issues.append(
                {
                    "code": ISSUE_RETURN_NOT_RECEIVED,
                    "message": (
                        "The order is marked returned but no refund or credit "
                        "settlement has been received yet."
                    ),
                }
            )
        status = (
            ReconciliationStatus.UNPAID_PAST_DUE
            if _is_past_due(order, now, settings.unpaid_past_due_days)
            else ReconciliationStatus.PENDING
        )
    elif effective_gap > tolerance:
        status = ReconciliationStatus.SHORT_PAID
    else:
        status = ReconciliationStatus.SETTLED
        if effective_gap < -tolerance:
            issues.append(
                {
                    "code": ISSUE_OVERPAID,
                    "message": f"Received {actual}, more than the expected {expected}.",
                    "amount": str((-effective_gap).quantize(CENTS)),
                }
            )

    return ReconciliationResult(
        run_id=run_id,
        is_current=True,
        order_id=order.id,
        settlement_record_id=linked[0].id if linked else None,
        import_batch_id=linked[0].import_batch_id if linked else None,
        status=status,
        currency=order.currency or "INR",
        expected_amount=expected,
        actual_amount=actual,
        difference_amount=difference,
        expected_freight_amount=expected_freight,
        actual_freight_amount=actual_freight,
        tcs_amount=tcs,
        tds_amount=tds,
        issues=issues or None,
        reconciled_at=now,
    )


def _build_orphan_result(
    settlement: SettlementRecord,
    extras: dict[tuple[str, str], _SettlementExtra],
    duplicates: dict[tuple[str, str], list[int]],
    now: datetime,
    run_id: int,
) -> ReconciliationResult:
    """Record a settlement that no order matched; never discard it."""
    key = (settlement.marketplace, settlement.external_reference)
    extra = extras.get(key, _SettlementExtra())
    actual = _dec(settlement.net_amount)

    if settlement.order_reference:
        issue = {
            "code": ISSUE_ORDER_NOT_FOUND,
            "message": (
                f"No order {settlement.order_reference!r} exists for this "
                f"settlement in {settlement.marketplace!r}."
            ),
        }
    else:
        issue = {
            "code": ISSUE_MISSING_REFERENCE,
            "message": "The settlement line carries no order or transaction reference.",
        }

    issues: list[dict[str, Any]] = [issue]
    if key in duplicates:
        issues.append(
            {
                "code": ISSUE_DUPLICATE_SETTLEMENT,
                "message": "The same settlement line was received more than once.",
                "references": [settlement.external_reference],
            }
        )

    return ReconciliationResult(
        run_id=run_id,
        is_current=True,
        order_id=None,
        settlement_record_id=settlement.id,
        import_batch_id=settlement.import_batch_id,
        status=ReconciliationStatus.MISSING_IN_ORDERS,
        currency=settlement.currency or "INR",
        expected_amount=ZERO,
        actual_amount=actual,
        difference_amount=(-actual).quantize(CENTS),
        expected_freight_amount=ZERO,
        actual_freight_amount=extra.freight,
        tcs_amount=extra.tcs,
        tds_amount=extra.tds,
        issues=issues,
        reconciled_at=now,
    )


def _source_watermark(db: Session) -> int | None:
    """Highest completed import batch id that contributed to reconciliation.

    A cheap, monotonic marker of "how much imported data this run consumed": a
    later run with a higher watermark necessarily read new batches.
    """
    highest = db.scalar(
        select(func.max(ImportBatch.id)).where(
            ImportBatch.status == ImportBatchStatus.COMPLETED,
            ImportBatch.source_type.in_(ORDER_SOURCE_TYPES + SETTLEMENT_SOURCE_TYPES),
        )
    )
    return int(highest) if highest is not None else None


def run_reconciliation(
    db: Session, *, triggered_by_user_id: int | None = None
) -> RunSummary:
    """Recompute every reconciliation result, preserving the previous ones.

    Each call creates a new :class:`~app.models.ReconciliationRun`, supersedes the
    previous run and its result lines, and writes the fresh results against the
    new run. Nothing is deleted: every past snapshot stays queryable. Because the
    projection upserts orders and settlements by natural key, the *current* result
    set is identical between two runs over unchanged data (idempotent).
    """
    attributes = _project_orders(db)
    extras, duplicates = _project_settlements(db)
    db.flush()

    orders = list(db.scalars(select(Order)).all())
    settlements = list(db.scalars(select(SettlementRecord)).all())

    _link_settlements(db, orders)
    db.flush()

    started_at = _now()
    watermark = _source_watermark(db)

    # Supersede, never delete: the previous run and its lines remain in the
    # database for audit but stop being "current".
    db.execute(
        update(ReconciliationRun)
        .where(ReconciliationRun.is_current.is_(True))
        .values(is_current=False)
    )
    db.execute(
        update(ReconciliationResult)
        .where(ReconciliationResult.is_current.is_(True))
        .values(is_current=False)
    )

    run = ReconciliationRun(
        started_at=started_at,
        triggered_by_user_id=triggered_by_user_id,
        source_watermark=watermark,
        is_current=True,
    )
    db.add(run)
    db.flush()  # assigns run.id

    by_order: dict[int, list[SettlementRecord]] = {}
    orphans: list[SettlementRecord] = []
    for settlement in settlements:
        if settlement.order_id is None:
            orphans.append(settlement)
        else:
            by_order.setdefault(settlement.order_id, []).append(settlement)

    now = _now()
    results: list[ReconciliationResult] = []
    by_status: dict[str, int] = {status.value: 0 for status in ReconciliationStatus}

    for order in orders:
        result = _build_order_result(
            db,
            order,
            attributes.get((order.marketplace, order.external_order_id)),
            by_order.get(order.id, []),
            extras,
            duplicates,
            now,
            run.id,
        )
        results.append(result)
        by_status[result.status.value] += 1

    for settlement in orphans:
        result = _build_orphan_result(settlement, extras, duplicates, now, run.id)
        results.append(result)
        by_status[result.status.value] += 1

    db.add_all(results)

    matched = sum(len(linked) for linked in by_order.values())
    finished_at = _now()
    run.finished_at = finished_at
    run.orders_reconciled = len(orders)
    run.settlements_matched = matched
    run.unmatched_settlements = len(orphans)
    run.results_created = len(results)
    run.by_status = by_status

    db.commit()

    return RunSummary(
        run_id=run.id,
        started_at=started_at,
        finished_at=finished_at,
        source_watermark=watermark,
        triggered_by_user_id=triggered_by_user_id,
        orders_reconciled=len(orders),
        settlements_matched=matched,
        unmatched_settlements=len(orphans),
        results_created=len(results),
        by_status=by_status,
    )


# --- Queries ---------------------------------------------------------------


def _scope_to_run(statement, *, run_id: int | None):
    """Restrict a result query to one run, or to the latest current run.

    The default views read the current run (``is_current`` is True only for the
    most recent run's lines); passing an explicit ``run_id`` reads that run's
    preserved snapshot instead.
    """
    if run_id is not None:
        return statement.where(ReconciliationResult.run_id == run_id)
    return statement.where(ReconciliationResult.is_current.is_(True))


def _filtered_statement(
    *,
    status: ReconciliationStatus | None,
    marketplace: str | None,
    has_issues: bool | None,
    run_id: int | None,
):
    statement = _scope_to_run(select(ReconciliationResult), run_id=run_id)
    if marketplace:
        statement = statement.outerjoin(
            Order, ReconciliationResult.order_id == Order.id
        ).outerjoin(
            SettlementRecord,
            ReconciliationResult.settlement_record_id == SettlementRecord.id,
        )
        statement = statement.where(
            or_(Order.marketplace == marketplace, SettlementRecord.marketplace == marketplace)
        )
    if status is not None:
        statement = statement.where(ReconciliationResult.status == status)
    if has_issues is True:
        statement = statement.where(ReconciliationResult.issues.isnot(None))
    elif has_issues is False:
        statement = statement.where(ReconciliationResult.issues.is_(None))
    return statement


def list_results(
    db: Session,
    *,
    status: ReconciliationStatus | None = None,
    marketplace: str | None = None,
    has_issues: bool | None = None,
    run_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ReconciliationResult], int]:
    """Return a page of results plus the matching total, newest first.

    Reads the current run by default; pass ``run_id`` to read a past run's
    preserved snapshot instead.
    """
    base = _filtered_statement(
        status=status, marketplace=marketplace, has_issues=has_issues, run_id=run_id
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        db.scalars(
            base.options(
                selectinload(ReconciliationResult.order),
                selectinload(ReconciliationResult.settlement_record),
                selectinload(ReconciliationResult.import_batch),
            )
            .order_by(ReconciliationResult.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return rows, int(total)


def get_result(db: Session, result_id: int) -> ReconciliationResult | None:
    """Load one result with its evidence, or ``None``.

    Any line is addressable by id — current or superseded — so a past run's
    evidence stays reachable.
    """
    return db.scalar(
        select(ReconciliationResult)
        .options(
            selectinload(ReconciliationResult.order),
            selectinload(ReconciliationResult.settlement_record),
            selectinload(ReconciliationResult.import_batch),
        )
        .where(ReconciliationResult.id == result_id)
    )


def current_run(db: Session) -> ReconciliationRun | None:
    """Return the latest run, or ``None`` if reconciliation has never run."""
    return db.scalar(
        select(ReconciliationRun)
        .options(selectinload(ReconciliationRun.triggered_by))
        .where(ReconciliationRun.is_current.is_(True))
    )


def get_run(db: Session, run_id: int) -> ReconciliationRun | None:
    """Load one run with its triggering user, or ``None``."""
    return db.scalar(
        select(ReconciliationRun)
        .options(selectinload(ReconciliationRun.triggered_by))
        .where(ReconciliationRun.id == run_id)
    )


def list_runs(
    db: Session, *, limit: int = 50, offset: int = 0
) -> tuple[list[ReconciliationRun], int]:
    """Return a page of runs, newest first, plus the total count."""
    total = db.scalar(select(func.count()).select_from(ReconciliationRun)) or 0
    rows = list(
        db.scalars(
            select(ReconciliationRun)
            .options(selectinload(ReconciliationRun.triggered_by))
            .order_by(ReconciliationRun.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return rows, int(total)


def summarize(
    db: Session,
    *,
    marketplace: str | None = None,
    run_id: int | None = None,
) -> dict[str, Any]:
    """Aggregate one run's results: totals, per-status counts and leakage.

    Reads the current run by default; pass ``run_id`` to summarise a past run's
    preserved snapshot. ``run_id`` in the result identifies the run summarised.
    """
    settings = get_settings()
    freight_tolerance = Decimal(settings.freight_overcharge_tolerance)

    effective_run_id = run_id
    if effective_run_id is None:
        effective_run_id = db.scalar(
            select(ReconciliationRun.id).where(ReconciliationRun.is_current.is_(True))
        )

    #: Revenue leakage is money that was due but not received: a short payment
    #: or an overdue unpaid order. Orders still within their due window
    #: (``pending``) are not leakage yet, and unmatched receipts are not leakage
    #: either. Statutory withholding is subtracted because it is not a loss.
    leakage = ReconciliationResult.difference_amount - (
        ReconciliationResult.tcs_amount + ReconciliationResult.tds_amount
    )
    leakage_condition = (leakage > 0) & ReconciliationResult.status.in_(
        (ReconciliationStatus.SHORT_PAID, ReconciliationStatus.UNPAID_PAST_DUE)
    )
    overcharge = (
        ReconciliationResult.actual_freight_amount
        - ReconciliationResult.expected_freight_amount
    )

    aggregate = _scope_to_run(
        select(
            func.count(ReconciliationResult.id),
            func.coalesce(func.sum(ReconciliationResult.expected_amount), 0),
            func.coalesce(func.sum(ReconciliationResult.actual_amount), 0),
            func.coalesce(func.sum(ReconciliationResult.difference_amount), 0),
            func.coalesce(func.sum(ReconciliationResult.tcs_amount), 0),
            func.coalesce(func.sum(ReconciliationResult.tds_amount), 0),
            func.coalesce(func.sum(case((leakage_condition, leakage), else_=0)), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (ReconciliationResult.expected_freight_amount > 0)
                            & (overcharge > freight_tolerance),
                            overcharge,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ),
        run_id=run_id,
    )
    if marketplace:
        aggregate = aggregate.outerjoin(
            Order, ReconciliationResult.order_id == Order.id
        ).outerjoin(
            SettlementRecord,
            ReconciliationResult.settlement_record_id == SettlementRecord.id,
        ).where(
            or_(Order.marketplace == marketplace, SettlementRecord.marketplace == marketplace)
        )

    row = db.execute(aggregate).one()
    (
        total,
        expected_total,
        actual_total,
        difference_total,
        tcs_total,
        tds_total,
        leakage_total,
        overcharge_total,
    ) = row

    counts = _scope_to_run(
        select(ReconciliationResult.status, func.count(ReconciliationResult.id)).group_by(
            ReconciliationResult.status
        ),
        run_id=run_id,
    )
    if marketplace:
        counts = counts.outerjoin(
            Order, ReconciliationResult.order_id == Order.id
        ).outerjoin(
            SettlementRecord,
            ReconciliationResult.settlement_record_id == SettlementRecord.id,
        ).where(
            or_(Order.marketplace == marketplace, SettlementRecord.marketplace == marketplace)
        )

    by_status = {status.value: 0 for status in ReconciliationStatus}
    for status_value, count in db.execute(counts).all():
        by_status[status_value.value if hasattr(status_value, "value") else str(status_value)] = int(count)

    return {
        "run_id": int(effective_run_id) if effective_run_id is not None else None,
        "total": int(total or 0),
        "by_status": by_status,
        "expected_total": _dec(expected_total),
        "actual_total": _dec(actual_total),
        "difference_total": _dec(difference_total),
        "tcs_total": _dec(tcs_total),
        "tds_total": _dec(tds_total),
        "revenue_leakage_total": _dec(leakage_total),
        "freight_overcharge_total": _dec(overcharge_total),
    }
