"""Service-level tests for the reconciliation engine.

Every scenario here drives :func:`app.reconciliation.service.run_reconciliation`
against in-memory SQLite, with the import batches and raw rows built directly so
the engine is exercised without going through the whole upload pipeline.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.roles import RoleName
from app.core.security import hash_password
from app.models import (
    FreightPaymentType,
    FreightRateCard,
    FreightServiceType,
    ImportBatch,
    ImportBatchStatus,
    ImportSourceType,
    Order,
    RawImportedRecord,
    ReconciliationResult,
    ReconciliationRun,
    ReconciliationStatus,
    Role,
    SettlementRecord,
    UploadedFile,
    User,
)
from app.reconciliation import service

PAST = "2020-01-05"
FUTURE = "2999-01-05"


# --- Fixtures and helpers --------------------------------------------------


def _make_batch(
    db: Session,
    *,
    source_type: ImportSourceType,
    partner: str,
    rows: list[dict[str, object]],
) -> ImportBatch:
    """Create a completed import batch with valid raw rows."""
    uploaded = UploadedFile(
        original_filename=f"{source_type.value}.csv",
        content_type="text/csv",
        size_bytes=1,
    )
    batch = ImportBatch(
        uploaded_file=uploaded,
        source_type=source_type,
        marketplace=partner,
        status=ImportBatchStatus.COMPLETED,
        total_rows=len(rows),
        processed_rows=len(rows),
    )
    db.add(batch)
    db.flush()
    for position, normalized in enumerate(rows, start=1):
        db.add(
            RawImportedRecord(
                import_batch_id=batch.id,
                row_number=position,
                raw_data=dict(normalized),
                normalized_data=dict(normalized),
                is_valid=True,
            )
        )
    db.commit()
    return batch


def _order_row(order_id: str, *, amount: str = "100.00", date: str = PAST, **extra: object):
    row: dict[str, object] = {
        "external_order_id": order_id,
        "order_date": date,
        "order_amount": amount,
        "order_status": "delivered",
    }
    row.update(extra)
    return row


def _settlement_row(
    *,
    transaction_reference: str | None = None,
    order_reference: str | None = None,
    amount: str = "100.00",
    date: str = PAST,
    **extra: object,
):
    row: dict[str, object] = {"settlement_amount": amount, "order_date": date}
    if transaction_reference is not None:
        row["transaction_reference"] = transaction_reference
    if order_reference is not None:
        row["external_order_id"] = order_reference
    row.update(extra)
    return row


def _seed(
    db: Session,
    *,
    orders: list[dict[str, object]] | None = None,
    settlements: list[dict[str, object]] | None = None,
    partner: str = "amazon",
    settlement_source: ImportSourceType = ImportSourceType.SETTLEMENTS,
) -> None:
    if orders:
        _make_batch(db, source_type=ImportSourceType.ORDERS, partner=partner, rows=orders)
    if settlements:
        _make_batch(db, source_type=settlement_source, partner=partner, rows=settlements)


def _results(db: Session) -> list[ReconciliationResult]:
    """The *current* reconciliation lines (the latest run's), oldest first."""
    return list(
        db.scalars(
            select(ReconciliationResult)
            .where(ReconciliationResult.is_current.is_(True))
            .order_by(ReconciliationResult.id)
        ).all()
    )


def _all_results(db: Session) -> list[ReconciliationResult]:
    """Every result ever written, including superseded runs (audit history)."""
    return list(
        db.scalars(select(ReconciliationResult).order_by(ReconciliationResult.id)).all()
    )


def _only(db: Session) -> ReconciliationResult:
    rows = _results(db)
    assert len(rows) == 1, f"expected exactly one result, got {len(rows)}"
    return rows[0]


def _codes(result: ReconciliationResult) -> set[str]:
    return {issue["code"] for issue in (result.issues or [])}


def _add_rate_card(
    db: Session,
    *,
    courier: str = "Delhivery",
    zone: str = "A",
    service_type: FreightServiceType = FreightServiceType.FORWARD,
    payment_type: FreightPaymentType = FreightPaymentType.PREPAID,
    min_grams: str = "0",
    max_grams: str = "2000",
    rate: str = "50.00",
) -> None:
    db.add(
        FreightRateCard(
            courier=courier,
            zone=zone,
            service_type=service_type,
            payment_type=payment_type,
            min_weight_grams=Decimal(min_grams),
            max_weight_grams=Decimal(max_grams),
            rate=Decimal(rate),
        )
    )
    db.commit()


# --- Payment states --------------------------------------------------------


def test_exact_payment_is_settled(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="100.00")
        ],
    )

    summary = service.run_reconciliation(db_session)

    assert summary.orders_reconciled == 1
    assert summary.settlements_matched == 1
    assert summary.unmatched_settlements == 0

    result = _only(db_session)
    assert result.status is ReconciliationStatus.SETTLED
    assert result.expected_amount == Decimal("100.00")
    assert result.actual_amount == Decimal("100.00")
    assert result.difference_amount == Decimal("0.00")


def test_short_payment_is_short_paid(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="80.00")
        ],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.SHORT_PAID
    assert result.difference_amount == Decimal("20.00")


def test_small_shortfall_within_tolerance_is_settled(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="99.50")
        ],
    )

    service.run_reconciliation(db_session)

    assert _only(db_session).status is ReconciliationStatus.SETTLED


def test_overpayment_is_settled_and_flagged(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="150.00")
        ],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.SETTLED
    assert service.ISSUE_OVERPAID in _codes(result)


def test_unpaid_order_past_due(db_session: Session) -> None:
    _seed(db_session, orders=[_order_row("A-1", amount="100.00", date=PAST)])

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.UNPAID_PAST_DUE
    assert result.actual_amount == Decimal("0.00")


def test_unpaid_recent_order_is_pending(db_session: Session) -> None:
    _seed(db_session, orders=[_order_row("A-1", amount="100.00", date=FUTURE)])

    service.run_reconciliation(db_session)

    assert _only(db_session).status is ReconciliationStatus.PENDING


# --- Multiple / partial settlements ---------------------------------------


def test_multiple_partial_settlements_sum_to_settled(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="60.00"),
            _settlement_row(transaction_reference="T-2", order_reference="A-1", amount="40.00"),
        ],
    )

    summary = service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.SETTLED
    assert result.actual_amount == Decimal("100.00")
    assert summary.settlements_matched == 2


def test_multiple_partial_settlements_below_expected_is_short_paid(
    db_session: Session,
) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="30.00"),
            _settlement_row(transaction_reference="T-2", order_reference="A-1", amount="40.00"),
        ],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.SHORT_PAID
    assert result.difference_amount == Decimal("30.00")


# --- Duplicates ------------------------------------------------------------


def test_duplicate_settlement_is_flagged_and_counted_once(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="100.00"),
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="100.00"),
        ],
    )

    service.run_reconciliation(db_session)

    # One stored settlement, one reconciliation line, counted once.
    assert db_session.scalar(select(func.count()).select_from(SettlementRecord)) == 1
    result = _only(db_session)
    assert result.actual_amount == Decimal("100.00")
    assert result.status is ReconciliationStatus.SETTLED
    assert service.ISSUE_DUPLICATE_SETTLEMENT in _codes(result)


# --- COD -------------------------------------------------------------------


def test_cod_remittance_short_payment(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00", payment_mode="COD")],
        settlements=[
            _settlement_row(transaction_reference="C-1", order_reference="A-1", amount="90.00")
        ],
        settlement_source=ImportSourceType.COD_REMITTANCES,
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.SHORT_PAID
    assert result.difference_amount == Decimal("10.00")


# --- TCS / TDS -------------------------------------------------------------


def test_tcs_and_tds_are_separate_and_not_leakage(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(
                transaction_reference="T-1",
                order_reference="A-1",
                amount="90.00",
                tcs_amount="5.00",
                tds_amount="5.00",
            )
        ],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    # The raw gap is 10.00 but it is fully explained by withholding.
    assert result.difference_amount == Decimal("10.00")
    assert result.tcs_amount == Decimal("5.00")
    assert result.tds_amount == Decimal("5.00")
    assert result.status is ReconciliationStatus.SETTLED

    summary = service.summarize(db_session)
    assert summary["revenue_leakage_total"] == Decimal("0.00")
    assert summary["tcs_total"] == Decimal("5.00")
    assert summary["tds_total"] == Decimal("5.00")


def test_withholding_does_not_hide_a_genuine_shortfall(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(
                transaction_reference="T-1",
                order_reference="A-1",
                amount="80.00",
                tcs_amount="5.00",
                tds_amount="5.00",
            )
        ],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.SHORT_PAID
    assert service.summarize(db_session)["revenue_leakage_total"] == Decimal("10.00")


# --- Freight ---------------------------------------------------------------


def test_freight_overcharge_beyond_tolerance_is_flagged(db_session: Session) -> None:
    _add_rate_card(db_session, rate="50.00")
    _seed(
        db_session,
        orders=[
            _order_row(
                "A-1",
                amount="100.00",
                courier_name="Delhivery",
                zone="A",
                weight_grams="1000",
            )
        ],
        settlements=[
            _settlement_row(
                transaction_reference="T-1",
                order_reference="A-1",
                amount="100.00",
                shipping_charge="70.00",
            )
        ],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.expected_freight_amount == Decimal("50.00")
    assert result.actual_freight_amount == Decimal("70.00")
    assert service.ISSUE_FREIGHT_OVERCHARGED in _codes(result)


def test_freight_within_tolerance_is_not_flagged(db_session: Session) -> None:
    _add_rate_card(db_session, rate="50.00")
    _seed(
        db_session,
        orders=[
            _order_row(
                "A-1", amount="100.00", courier_name="Delhivery", zone="A", weight_grams="1000"
            )
        ],
        settlements=[
            _settlement_row(
                transaction_reference="T-1",
                order_reference="A-1",
                amount="100.00",
                shipping_charge="55.00",
            )
        ],
    )

    service.run_reconciliation(db_session)

    assert service.ISSUE_FREIGHT_OVERCHARGED not in _codes(_only(db_session))


def test_reverse_shipment_uses_the_reverse_rate(db_session: Session) -> None:
    _add_rate_card(
        db_session,
        service_type=FreightServiceType.REVERSE,
        rate="120.00",
    )
    _seed(
        db_session,
        orders=[
            _order_row(
                "A-1",
                amount="100.00",
                order_status="Returned",
                courier_name="Delhivery",
                zone="A",
                weight_grams="1000",
            )
        ],
        settlements=[
            _settlement_row(
                transaction_reference="T-1",
                order_reference="A-1",
                amount="100.00",
                shipping_charge="150.00",
            )
        ],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.expected_freight_amount == Decimal("120.00")
    assert service.ISSUE_FREIGHT_OVERCHARGED in _codes(result)


def test_missing_rate_card_produces_no_freight_expectation(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(
                transaction_reference="T-1",
                order_reference="A-1",
                amount="100.00",
                shipping_charge="999.00",
            )
        ],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.expected_freight_amount == Decimal("0.00")
    # A missing rate card is a configuration gap, not an overcharge.
    assert service.ISSUE_FREIGHT_OVERCHARGED not in _codes(result)


# --- Unmatched records -----------------------------------------------------


def test_settlement_referencing_unknown_order_is_flagged(db_session: Session) -> None:
    _seed(
        db_session,
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="GHOST-9", amount="75.00")
        ],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.MISSING_IN_ORDERS
    assert result.order_id is None
    assert result.actual_amount == Decimal("75.00")
    assert result.difference_amount == Decimal("-75.00")
    assert service.ISSUE_ORDER_NOT_FOUND in _codes(result)


def test_settlement_without_any_reference_is_kept_and_flagged(db_session: Session) -> None:
    _seed(
        db_session,
        settlements=[_settlement_row(amount="75.00")],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.MISSING_IN_ORDERS
    assert service.ISSUE_MISSING_REFERENCE in _codes(result)


def test_unmatched_settlements_are_never_discarded(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="100.00"),
            _settlement_row(transaction_reference="T-2", order_reference="GHOST-1", amount="10.00"),
            _settlement_row(amount="20.00"),
        ],
    )

    summary = service.run_reconciliation(db_session)

    assert summary.results_created == 3
    assert summary.unmatched_settlements == 2


# --- Returns ---------------------------------------------------------------


def test_returned_order_without_credit_is_flagged(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00", order_status="Returned", date=PAST)],
    )

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.UNPAID_PAST_DUE
    assert service.ISSUE_RETURN_NOT_RECEIVED in _codes(result)


# --- Idempotency -----------------------------------------------------------


def test_rerun_is_idempotent(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00"), _order_row("A-2", amount="50.00", date=FUTURE)],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="100.00")
        ],
    )

    first = service.run_reconciliation(db_session)
    snapshot = [
        (r.status, r.expected_amount, r.actual_amount, r.difference_amount)
        for r in _results(db_session)
    ]

    second = service.run_reconciliation(db_session)

    # Orders and settlements are upserted by natural key: never duplicated.
    assert second.results_created == first.results_created
    assert db_session.scalar(select(func.count()).select_from(Order)) == 2
    assert db_session.scalar(select(func.count()).select_from(SettlementRecord)) == 1
    # The *current* lines are identical between the two runs ...
    assert [
        (r.status, r.expected_amount, r.actual_amount, r.difference_amount)
        for r in _results(db_session)
    ] == snapshot
    # ... and the previous run's lines are preserved, not deleted: 2 + 2 rows.
    assert len(_all_results(db_session)) == 4
    assert all(r.run_id == second.run_id for r in _results(db_session))


def test_reprocessing_an_import_does_not_create_a_false_duplicate(
    db_session: Session,
) -> None:
    """Re-processing re-creates raw rows with new ids; that is not a duplicate."""
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="100.00")
        ],
    )
    service.run_reconciliation(db_session)

    # Simulate a re-process: raw rows are deleted and written again.
    original = db_session.scalars(select(RawImportedRecord)).all()
    rows = [(r.import_batch_id, r.row_number, dict(r.raw_data)) for r in original]
    for record in original:
        db_session.delete(record)
    db_session.commit()
    for batch_id, row_number, raw in rows:
        db_session.add(
            RawImportedRecord(
                import_batch_id=batch_id,
                row_number=row_number,
                raw_data=raw,
                normalized_data=raw,
                is_valid=True,
            )
        )
    db_session.commit()

    service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.status is ReconciliationStatus.SETTLED
    assert service.ISSUE_DUPLICATE_SETTLEMENT not in _codes(result)


# --- Aggregation, filtering, pagination -----------------------------------


def test_summarize_aggregates_totals(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[
            _order_row("A-1", amount="100.00"),
            _order_row("A-2", amount="200.00"),
            _order_row("A-3", amount="300.00", date=FUTURE),
        ],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="100.00"),
            _settlement_row(transaction_reference="T-2", order_reference="A-2", amount="150.00"),
        ],
    )
    service.run_reconciliation(db_session)

    summary = service.summarize(db_session)

    assert summary["total"] == 3
    assert summary["expected_total"] == Decimal("600.00")
    assert summary["actual_total"] == Decimal("250.00")
    assert summary["by_status"][ReconciliationStatus.SETTLED.value] == 1
    assert summary["by_status"][ReconciliationStatus.SHORT_PAID.value] == 1
    assert summary["by_status"][ReconciliationStatus.PENDING.value] == 1
    assert summary["revenue_leakage_total"] == Decimal("50.00")


def test_list_results_filters_by_status_and_marketplace(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00", date=PAST)],
        partner="amazon",
    )
    _seed(
        db_session,
        orders=[_order_row("F-1", amount="100.00", date=FUTURE)],
        partner="flipkart",
    )
    service.run_reconciliation(db_session)

    rows, total = service.list_results(
        db_session, status=ReconciliationStatus.PENDING
    )
    assert total == 1
    assert rows[0].status is ReconciliationStatus.PENDING

    rows, total = service.list_results(db_session, marketplace="amazon")
    assert total == 1
    assert rows[0].order.marketplace == "amazon"


def test_list_results_filters_by_issues(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="150.00")
        ],
    )
    service.run_reconciliation(db_session)

    with_issues, with_total = service.list_results(db_session, has_issues=True)
    without_issues, without_total = service.list_results(db_session, has_issues=False)

    assert with_total == 1
    assert with_issues[0].issues
    assert without_total == 0
    assert without_issues == []


def test_list_results_paginate(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row(f"A-{i}", amount="100.00") for i in range(5)],
    )
    service.run_reconciliation(db_session)

    page, total = service.list_results(db_session, limit=2, offset=1)

    assert total == 5
    assert len(page) == 2


# --- Scale and query performance ------------------------------------------


def test_large_dataset_reconciles_every_record(db_session: Session) -> None:
    count = 300
    _seed(
        db_session,
        orders=[_order_row(f"A-{i}", amount="100.00") for i in range(count)],
        settlements=[
            _settlement_row(
                transaction_reference=f"T-{i}", order_reference=f"A-{i}", amount="100.00"
            )
            for i in range(count)
        ],
    )

    summary = service.run_reconciliation(db_session)

    assert summary.orders_reconciled == count
    assert summary.results_created == count
    assert summary.by_status[ReconciliationStatus.SETTLED.value] == count


def test_query_performance_on_a_large_result_set(db_session: Session) -> None:
    import time

    count = 1000
    _seed(
        db_session,
        orders=[_order_row(f"A-{i}", amount="100.00") for i in range(count)],
    )
    service.run_reconciliation(db_session)

    started = time.perf_counter()
    page, total = service.list_results(db_session, limit=50)
    elapsed = time.perf_counter() - started

    assert total == count
    assert len(page) == 50
    # A generous ceiling: this only guards against an accidental N+1 blow-up.
    assert elapsed < 5.0


def test_run_with_no_imported_data_is_a_no_op(db_session: Session) -> None:
    summary = service.run_reconciliation(db_session)

    assert summary.results_created == 0
    assert summary.orders_reconciled == 0
    assert service.summarize(db_session)["total"] == 0


# --- Run history -----------------------------------------------------------


def _make_user(db: Session, *, email: str = "finance@example.com") -> User:
    role = Role(name=RoleName.FINANCE_EXECUTIVE.value)
    db.add(role)
    db.flush()
    user = User(
        email=email,
        full_name="Finance",
        password_hash=hash_password("correct-horse-battery-staple"),
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    return user


def test_run_records_identity_and_counts(db_session: Session) -> None:
    _seed(
        db_session,
        orders=[_order_row("A-1", amount="100.00")],
        settlements=[
            _settlement_row(transaction_reference="T-1", order_reference="A-1", amount="100.00")
        ],
    )

    summary = service.run_reconciliation(db_session)

    run = service.get_run(db_session, summary.run_id)
    assert run is not None
    assert run.is_current is True
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.orders_reconciled == 1
    assert run.settlements_matched == 1
    assert run.unmatched_settlements == 0
    assert run.results_created == 1
    assert run.by_status[ReconciliationStatus.SETTLED.value] == 1
    # The watermark is the highest completed import batch consumed by the run.
    assert run.source_watermark is not None


def test_run_records_the_triggering_user(db_session: Session) -> None:
    _seed(db_session, orders=[_order_row("A-1", amount="100.00")])
    user = _make_user(db_session)

    summary = service.run_reconciliation(db_session, triggered_by_user_id=user.id)

    run = service.get_run(db_session, summary.run_id)
    assert run.triggered_by_user_id == user.id
    assert run.triggered_by is not None
    assert run.triggered_by.email == "finance@example.com"


def test_result_lines_carry_the_run_id_and_current_flag(db_session: Session) -> None:
    _seed(db_session, orders=[_order_row("A-1", amount="100.00")])

    summary = service.run_reconciliation(db_session)

    result = _only(db_session)
    assert result.run_id == summary.run_id
    assert result.is_current is True


def test_second_run_supersedes_the_first(db_session: Session) -> None:
    _seed(db_session, orders=[_order_row("A-1", amount="100.00")])

    first = service.run_reconciliation(db_session)
    second = service.run_reconciliation(db_session)

    first_run = service.get_run(db_session, first.run_id)
    second_run = service.get_run(db_session, second.run_id)
    assert first_run.is_current is False
    assert second_run.is_current is True

    current = service.current_run(db_session)
    assert current is not None
    assert current.id == second.run_id


def test_exactly_one_run_is_current_across_many_runs(db_session: Session) -> None:
    _seed(db_session, orders=[_order_row("A-1", amount="100.00")])
    service.run_reconciliation(db_session)
    service.run_reconciliation(db_session)
    service.run_reconciliation(db_session)

    current = db_session.scalars(
        select(ReconciliationRun).where(ReconciliationRun.is_current.is_(True))
    ).all()
    assert len(current) == 1
    assert service.list_runs(db_session)[1] == 3


def test_historical_results_are_preserved_and_scoped(db_session: Session) -> None:
    _seed(db_session, orders=[_order_row("A-1", amount="100.00")])
    first = service.run_reconciliation(db_session)

    # A later run that consumes a newly imported order changes the current set.
    _seed(db_session, orders=[_order_row("A-2", amount="50.00", date=FUTURE)])
    second = service.run_reconciliation(db_session)

    # The first run's snapshot is intact and still addressable by its run id.
    old_rows, old_total = service.list_results(db_session, run_id=first.run_id)
    assert old_total == 1
    assert old_rows[0].run_id == first.run_id
    assert old_rows[0].is_current is False

    # The default (current) view shows the latest run's two rows.
    cur_rows, cur_total = service.list_results(db_session)
    assert cur_total == 2
    assert all(row.run_id == second.run_id for row in cur_rows)
    assert all(row.is_current for row in cur_rows)


def test_list_runs_returns_newest_first(db_session: Session) -> None:
    _seed(db_session, orders=[_order_row("A-1", amount="100.00")])
    first = service.run_reconciliation(db_session)
    second = service.run_reconciliation(db_session)

    runs, total = service.list_runs(db_session)

    assert total == 2
    assert [run.id for run in runs] == [second.run_id, first.run_id]
    assert runs[0].is_current is True
    assert runs[1].is_current is False


def test_summarize_targets_a_historical_run(db_session: Session) -> None:
    _seed(db_session, orders=[_order_row("A-1", amount="100.00")])
    first = service.run_reconciliation(db_session)

    _seed(db_session, orders=[_order_row("A-2", amount="200.00")])
    second = service.run_reconciliation(db_session)

    current = service.summarize(db_session)
    assert current["run_id"] == second.run_id
    assert current["total"] == 2
    assert current["expected_total"] == Decimal("300.00")

    historical = service.summarize(db_session, run_id=first.run_id)
    assert historical["run_id"] == first.run_id
    assert historical["total"] == 1
    assert historical["expected_total"] == Decimal("100.00")
    # The first run saw a single, unpaid past-due order.
    assert historical["by_status"][ReconciliationStatus.UNPAID_PAST_DUE.value] == 1
    assert sum(historical["by_status"].values()) == 1


def test_summarize_on_an_empty_database_reports_no_run(db_session: Session) -> None:
    assert service.current_run(db_session) is None
    assert service.summarize(db_session)["run_id"] is None
    assert service.summarize(db_session)["total"] == 0
