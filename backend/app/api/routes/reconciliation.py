"""Reconciliation endpoints: run the engine and read its results.

These are thin wrappers over :mod:`app.reconciliation.service`. Reads require any
authenticated user; running the engine (which supersedes the previous run and
writes a fresh, preserved set of result rows) is restricted to the two internal
finance roles.

Reads default to the latest run; pass ``run_id`` to read a preserved past run.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_roles
from app.core.roles import RoleName
from app.db.session import get_db
from app.models import ReconciliationStatus, User
from app.reconciliation import service
from app.schemas.reconciliation import (
    ReconciliationResultPage,
    ReconciliationResultRead,
    ReconciliationRunDetailRead,
    ReconciliationRunPage,
    ReconciliationRunRead,
    ReconciliationSummaryRead,
)

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

#: Dependency for endpoints that supersede the current run.
ReconciliationOperator = Annotated[
    User,
    Depends(require_roles(RoleName.FINANCE_EXECUTIVE, RoleName.CO_FOUNDER)),
]

DbSession = Annotated[Session, Depends(get_db)]


@router.post("/run", response_model=ReconciliationRunRead)
def run_reconciliation(user: ReconciliationOperator, db: DbSession) -> ReconciliationRunRead:
    """Recompute every reconciliation result, preserving the previous run."""
    summary = service.run_reconciliation(db, triggered_by_user_id=user.id)
    run = service.get_run(db, summary.run_id)
    assert run is not None  # just created in this session
    return ReconciliationRunRead.from_model(run)


@router.get("/runs", response_model=ReconciliationRunPage)
def list_reconciliation_runs(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReconciliationRunPage:
    """List reconciliation runs, newest first, with the current one flagged."""
    rows, total = service.list_runs(db, limit=limit, offset=offset)
    return ReconciliationRunPage(
        total=total,
        returned=len(rows),
        limit=limit,
        offset=offset,
        rows=[ReconciliationRunRead.from_model(row) for row in rows],
    )


@router.get("/runs/{run_id}", response_model=ReconciliationRunDetailRead)
def get_reconciliation_run(
    run_id: int,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReconciliationRunDetailRead:
    """Return one run and the results it produced (its preserved snapshot)."""
    run = service.get_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation run {run_id} was not found.",
        )
    rows, total = service.list_results(db, run_id=run_id, limit=limit, offset=offset)
    return ReconciliationRunDetailRead(
        run=ReconciliationRunRead.from_model(run),
        results=ReconciliationResultPage(
            total=total,
            returned=len(rows),
            limit=limit,
            offset=offset,
            rows=[ReconciliationResultRead.from_model(row) for row in rows],
        ),
    )


@router.get("", response_model=ReconciliationResultPage)
def list_reconciliation_results(
    user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[ReconciliationStatus | None, Query(alias="status")] = None,
    marketplace: Annotated[str | None, Query()] = None,
    has_issues: Annotated[bool | None, Query()] = None,
    run_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReconciliationResultPage:
    """List reconciliation lines, newest first, from the latest run by default."""
    rows, total = service.list_results(
        db,
        status=status_filter,
        marketplace=marketplace,
        has_issues=has_issues,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )
    return ReconciliationResultPage(
        total=total,
        returned=len(rows),
        limit=limit,
        offset=offset,
        rows=[ReconciliationResultRead.from_model(row) for row in rows],
    )


@router.get("/summary", response_model=ReconciliationSummaryRead)
def reconciliation_summary(
    user: CurrentUser,
    db: DbSession,
    marketplace: Annotated[str | None, Query()] = None,
    run_id: Annotated[int | None, Query()] = None,
) -> ReconciliationSummaryRead:
    """Aggregate totals, per-status counts and revenue leakage for one run."""
    return ReconciliationSummaryRead(
        **service.summarize(db, marketplace=marketplace, run_id=run_id)
    )


@router.get("/{result_id}", response_model=ReconciliationResultRead)
def get_reconciliation_result(
    result_id: int, user: CurrentUser, db: DbSession
) -> ReconciliationResultRead:
    """Return one reconciliation line with its supporting evidence."""
    result = service.get_result(db, result_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation result {result_id} was not found.",
        )
    return ReconciliationResultRead.from_model(result)
