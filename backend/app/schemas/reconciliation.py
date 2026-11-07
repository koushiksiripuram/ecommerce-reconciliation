"""Request and response schemas for the reconciliation API.

Responses are built from ORM objects by ``from_model`` classmethods so exactly
which fields leave the API stays explicit and easy to audit. Monetary values are
serialised as exact :class:`~decimal.Decimal` values, never floats.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from pydantic import BaseModel, Field

from app.models import (
    Order,
    OrderStatus,
    ReconciliationResult,
    ReconciliationRun,
    ReconciliationStatus,
)
from app.models.settlement import SettlementRecord


class ReconciliationIssueRead(BaseModel):
    """A structured problem detected on a reconciliation line."""

    code: str
    message: str
    amount: Decimal | None = None
    references: list[str] = Field(default_factory=list)
    settlement_record_ids: list[int] = Field(default_factory=list)

    @classmethod
    def from_issue(cls, entry: Mapping[str, Any]) -> ReconciliationIssueRead:
        """Build an issue from the stored dictionary, ignoring unknown keys."""
        amount = entry.get("amount")
        return cls(
            code=str(entry.get("code", "")),
            message=str(entry.get("message", "")),
            amount=Decimal(str(amount)) if amount is not None else None,
            references=[str(value) for value in entry.get("references", [])],
            settlement_record_ids=[
                int(value) for value in entry.get("settlement_record_ids", [])
            ],
        )


class ReconciliationOrderRead(BaseModel):
    """The order a reconciliation line is about."""

    id: int
    external_order_id: str
    marketplace: str
    order_date: datetime | None
    status: OrderStatus

    @classmethod
    def from_model(cls, order: Order) -> ReconciliationOrderRead:
        return cls(
            id=order.id,
            external_order_id=order.external_order_id,
            marketplace=order.marketplace,
            order_date=order.order_date,
            status=order.status,
        )


class ReconciliationSettlementRead(BaseModel):
    """The settlement record used as evidence for a reconciliation line."""

    id: int
    marketplace: str
    external_reference: str
    order_reference: str | None
    settlement_date: datetime | None
    net_amount: Decimal
    import_batch_id: int | None

    @classmethod
    def from_model(cls, settlement: SettlementRecord) -> ReconciliationSettlementRead:
        return cls(
            id=settlement.id,
            marketplace=settlement.marketplace,
            external_reference=settlement.external_reference,
            order_reference=settlement.order_reference,
            settlement_date=settlement.settlement_date,
            net_amount=settlement.net_amount,
            import_batch_id=settlement.import_batch_id,
        )


class ReconciliationResultRead(BaseModel):
    """One reconciliation line: an order and the money received against it."""

    id: int
    status: ReconciliationStatus
    currency: str
    expected_amount: Decimal
    actual_amount: Decimal
    difference_amount: Decimal
    expected_freight_amount: Decimal
    actual_freight_amount: Decimal
    tcs_amount: Decimal
    tds_amount: Decimal
    issues: list[ReconciliationIssueRead]
    order: ReconciliationOrderRead | None
    settlement_record: ReconciliationSettlementRead | None
    import_batch_id: int | None
    run_id: int | None
    is_current: bool
    reconciled_at: datetime | None
    created_at: datetime | None

    @classmethod
    def from_model(cls, result: ReconciliationResult) -> ReconciliationResultRead:
        return cls(
            id=result.id,
            status=result.status,
            currency=result.currency,
            expected_amount=result.expected_amount,
            actual_amount=result.actual_amount,
            difference_amount=result.difference_amount,
            expected_freight_amount=result.expected_freight_amount,
            actual_freight_amount=result.actual_freight_amount,
            tcs_amount=result.tcs_amount,
            tds_amount=result.tds_amount,
            issues=[
                ReconciliationIssueRead.from_issue(entry)
                for entry in (result.issues or [])
            ],
            order=(
                ReconciliationOrderRead.from_model(result.order)
                if result.order is not None
                else None
            ),
            settlement_record=(
                ReconciliationSettlementRead.from_model(result.settlement_record)
                if result.settlement_record is not None
                else None
            ),
            import_batch_id=result.import_batch_id,
            run_id=result.run_id,
            is_current=result.is_current,
            reconciled_at=result.reconciled_at,
            created_at=result.created_at,
        )


class ReconciliationResultPage(BaseModel):
    """A page of reconciliation lines, newest first."""

    total: int
    returned: int
    limit: int
    offset: int
    rows: list[ReconciliationResultRead]


class ReconciliationRunRead(BaseModel):
    """A reconciliation run: its identity plus what it produced.

    Runs are immutable snapshots. Exactly one — the latest — is ``is_current``,
    and the default result/summary views read that one.
    """

    id: int
    started_at: datetime
    finished_at: datetime | None
    triggered_by_user_id: int | None
    triggered_by_email: str | None
    source_watermark: int | None
    orders_reconciled: int
    settlements_matched: int
    unmatched_settlements: int
    results_created: int
    by_status: dict[str, int]
    is_current: bool
    created_at: datetime | None

    @classmethod
    def from_model(cls, run: ReconciliationRun) -> ReconciliationRunRead:
        return cls(
            id=run.id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            triggered_by_user_id=run.triggered_by_user_id,
            triggered_by_email=(
                run.triggered_by.email if run.triggered_by is not None else None
            ),
            source_watermark=run.source_watermark,
            orders_reconciled=run.orders_reconciled,
            settlements_matched=run.settlements_matched,
            unmatched_settlements=run.unmatched_settlements,
            results_created=run.results_created,
            by_status=dict(run.by_status or {}),
            is_current=run.is_current,
            created_at=run.created_at,
        )


class ReconciliationRunPage(BaseModel):
    """A page of reconciliation runs, newest first."""

    total: int
    returned: int
    limit: int
    offset: int
    rows: list[ReconciliationRunRead]


class ReconciliationRunDetailRead(BaseModel):
    """One run together with the results it produced."""

    run: ReconciliationRunRead
    results: ReconciliationResultPage


class ReconciliationSummaryRead(BaseModel):
    """Aggregated reconciliation figures for one run."""

    run_id: int | None
    total: int
    by_status: dict[str, int]
    expected_total: Decimal
    actual_total: Decimal
    difference_total: Decimal
    tcs_total: Decimal
    tds_total: Decimal
    revenue_leakage_total: Decimal
    freight_overcharge_total: Decimal
