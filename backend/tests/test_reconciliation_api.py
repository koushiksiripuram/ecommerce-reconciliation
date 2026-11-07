"""End-to-end tests for the reconciliation API.

A real ``TestClient`` drives the app against in-memory SQLite with the database
dependency overridden, so authentication, role checks, filtering, pagination and
the four endpoints are exercised over real HTTP.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import RoleName
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    ImportBatch,
    ImportBatchStatus,
    ImportSourceType,
    RawImportedRecord,
    Role,
    UploadedFile,
    User,
)

PASSWORD = "correct-horse-battery-staple"
PAST = "2020-01-05"
FUTURE = "2999-01-05"

AuthHeaders = dict[str, str]


def _money(value: object) -> Decimal:
    """Normalise a serialised amount to a two-decimal Decimal."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


@pytest.fixture
def client(session_factory: sessionmaker[Session], upload_dir) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth(session_factory: sessionmaker[Session]) -> dict[str, AuthHeaders]:
    """Seed the roles/users and return ready-to-use bearer headers per persona."""
    with session_factory() as session:
        finance_role = Role(name=RoleName.FINANCE_EXECUTIVE.value)
        founder_role = Role(name=RoleName.CO_FOUNDER.value)
        auditor_role = Role(name="auditor")
        session.add_all([finance_role, founder_role, auditor_role])
        session.flush()

        finance = User(
            email="finance@example.com",
            full_name="Finance",
            password_hash=hash_password(PASSWORD),
            role_id=finance_role.id,
        )
        founder = User(
            email="founder@example.com",
            full_name="Founder",
            password_hash=hash_password(PASSWORD),
            role_id=founder_role.id,
        )
        auditor = User(
            email="auditor@example.com",
            full_name="Auditor",
            password_hash=hash_password(PASSWORD),
            role_id=auditor_role.id,
        )
        session.add_all([finance, founder, auditor])
        session.commit()

        return {
            "finance": {"Authorization": f"Bearer {create_access_token(finance.id, finance_role.name)}"},
            "founder": {"Authorization": f"Bearer {create_access_token(founder.id, founder_role.name)}"},
            "auditor": {"Authorization": f"Bearer {create_access_token(auditor.id, auditor_role.name)}"},
        }


def _add_batch(
    session: Session,
    *,
    source_type: ImportSourceType,
    partner: str,
    rows: list[dict[str, object]],
) -> None:
    uploaded = UploadedFile(
        original_filename=f"{source_type.value}.csv", content_type="text/csv", size_bytes=1
    )
    batch = ImportBatch(
        uploaded_file=uploaded,
        source_type=source_type,
        marketplace=partner,
        status=ImportBatchStatus.COMPLETED,
        total_rows=len(rows),
        processed_rows=len(rows),
    )
    session.add(batch)
    session.flush()
    for position, normalized in enumerate(rows, start=1):
        session.add(
            RawImportedRecord(
                import_batch_id=batch.id,
                row_number=position,
                raw_data=dict(normalized),
                normalized_data=dict(normalized),
                is_valid=True,
            )
        )
    session.commit()


def _seed(session_factory: sessionmaker[Session], *, partner: str = "amazon") -> None:
    """One settled order and one short-paid order for endpoint assertions."""
    with session_factory() as session:
        _add_batch(
            session,
            source_type=ImportSourceType.ORDERS,
            partner=partner,
            rows=[
                {
                    "external_order_id": "A-1",
                    "order_date": PAST,
                    "order_amount": "100.00",
                    "order_status": "delivered",
                },
                {
                    "external_order_id": "A-2",
                    "order_date": FUTURE,
                    "order_amount": "200.00",
                    "order_status": "delivered",
                },
            ],
        )
        _add_batch(
            session,
            source_type=ImportSourceType.SETTLEMENTS,
            partner=partner,
            rows=[
                {
                    "transaction_reference": "T-1",
                    "external_order_id": "A-1",
                    "order_date": PAST,
                    "settlement_amount": "100.00",
                },
            ],
        )


# --- authentication and RBAC ----------------------------------------------


def test_run_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/reconciliation/run").status_code == 401


def test_run_is_forbidden_for_an_unprivileged_role(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    assert client.post("/api/reconciliation/run", headers=auth["auditor"]).status_code == 403


def test_run_is_allowed_for_each_finance_role(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)

    response = client.post("/api/reconciliation/run", headers=auth["finance"])

    assert response.status_code == 200
    body = response.json()
    assert body["orders_reconciled"] == 2
    assert body["results_created"] == 2
    assert body["by_status"]["settled"] == 1
    assert body["by_status"]["pending"] == 1


def test_reads_require_authentication(client: TestClient) -> None:
    assert client.get("/api/reconciliation").status_code == 401
    assert client.get("/api/reconciliation/summary").status_code == 401
    assert client.get("/api/reconciliation/1").status_code == 401


def test_reads_are_allowed_for_an_unprivileged_role(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    client.post("/api/reconciliation/run", headers=auth["finance"])

    assert client.get("/api/reconciliation", headers=auth["auditor"]).status_code == 200


# --- listing ---------------------------------------------------------------


def test_list_returns_a_page_of_results(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    client.post("/api/reconciliation/run", headers=auth["finance"])

    response = client.get("/api/reconciliation", headers=auth["finance"])

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["returned"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["rows"]) == 2
    assert {"id", "status", "expected_amount", "actual_amount", "issues"} <= set(body["rows"][0])


def test_list_filters_by_status(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    client.post("/api/reconciliation/run", headers=auth["finance"])

    response = client.get("/api/reconciliation?status=settled", headers=auth["finance"])

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["status"] == "settled"


def test_list_filters_by_marketplace(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory, partner="amazon")
    client.post("/api/reconciliation/run", headers=auth["finance"])

    assert client.get("/api/reconciliation?marketplace=amazon", headers=auth["finance"]).json()["total"] == 2
    assert client.get("/api/reconciliation?marketplace=flipkart", headers=auth["finance"]).json()["total"] == 0


def test_list_paginates(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    client.post("/api/reconciliation/run", headers=auth["finance"])

    response = client.get("/api/reconciliation?limit=1&offset=1", headers=auth["finance"])

    body = response.json()
    assert body["total"] == 2
    assert body["returned"] == 1
    assert body["limit"] == 1
    assert body["offset"] == 1


def test_list_rejects_a_bad_limit(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    assert client.get("/api/reconciliation?limit=0", headers=auth["finance"]).status_code == 422


def test_list_rejects_an_unknown_status(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    assert client.get("/api/reconciliation?status=nope", headers=auth["finance"]).status_code == 422


# --- single result ---------------------------------------------------------


def test_get_result_returns_one_with_evidence(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    client.post("/api/reconciliation/run", headers=auth["finance"])
    settled = client.get("/api/reconciliation?status=settled", headers=auth["finance"]).json()
    result_id = settled["rows"][0]["id"]

    response = client.get(f"/api/reconciliation/{result_id}", headers=auth["finance"])

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == result_id
    assert body["status"] == "settled"
    assert body["order"] is not None
    assert body["settlement_record"] is not None
    assert _money(body["expected_amount"]) == Decimal("100.00")


def test_get_result_returns_404_for_an_unknown_id(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    assert client.get("/api/reconciliation/9999", headers=auth["finance"]).status_code == 404


# --- summary ---------------------------------------------------------------


def test_summary_route_is_not_shadowed_by_the_id_route(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    client.post("/api/reconciliation/run", headers=auth["finance"])

    response = client.get("/api/reconciliation/summary", headers=auth["finance"])

    assert response.status_code == 200
    assert "revenue_leakage_total" in response.json()


def test_summary_returns_aggregates(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    client.post("/api/reconciliation/run", headers=auth["finance"])

    body = client.get("/api/reconciliation/summary", headers=auth["finance"]).json()

    assert body["total"] == 2
    assert body["by_status"]["settled"] == 1
    assert body["by_status"]["pending"] == 1
    assert _money(body["expected_total"]) == Decimal("300.00")
    assert _money(body["actual_total"]) == Decimal("100.00")
    assert _money(body["revenue_leakage_total"]) == Decimal("0.00")


def test_full_workflow_run_then_read(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)

    run = client.post("/api/reconciliation/run", headers=auth["founder"])
    assert run.status_code == 200

    listing = client.get("/api/reconciliation", headers=auth["founder"])
    assert listing.status_code == 200
    assert listing.json()["total"] == 2

    summary = client.get("/api/reconciliation/summary", headers=auth["founder"])
    assert summary.status_code == 200
    assert summary.json()["total"] == 2


# --- run history -----------------------------------------------------------


def test_run_response_carries_the_run_identity(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)

    body = client.post("/api/reconciliation/run", headers=auth["finance"]).json()

    assert isinstance(body["id"], int)
    assert body["is_current"] is True
    assert body["started_at"] is not None
    assert body["finished_at"] is not None
    assert body["triggered_by_user_id"] is not None
    assert body["triggered_by_email"] == "finance@example.com"
    assert body["source_watermark"] is not None
    assert body["results_created"] == 2


def test_list_results_expose_run_id_and_current_flag(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    run = client.post("/api/reconciliation/run", headers=auth["finance"]).json()

    rows = client.get("/api/reconciliation", headers=auth["finance"]).json()["rows"]

    assert all(row["run_id"] == run["id"] for row in rows)
    assert all(row["is_current"] is True for row in rows)


def test_runs_endpoint_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/reconciliation/runs").status_code == 401


def test_runs_are_not_shadowed_by_the_id_route(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    client.post("/api/reconciliation/run", headers=auth["finance"])

    response = client.get("/api/reconciliation/runs", headers=auth["finance"])

    assert response.status_code == 200
    assert "rows" in response.json()


def test_runs_endpoint_lists_runs_newest_first(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    first = client.post("/api/reconciliation/run", headers=auth["finance"]).json()
    second = client.post("/api/reconciliation/run", headers=auth["finance"]).json()

    body = client.get("/api/reconciliation/runs", headers=auth["finance"]).json()

    assert body["total"] == 2
    assert [row["id"] for row in body["rows"]] == [second["id"], first["id"]]
    assert body["rows"][0]["is_current"] is True
    assert body["rows"][1]["is_current"] is False


def test_run_detail_returns_that_runs_results(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    run = client.post("/api/reconciliation/run", headers=auth["finance"]).json()

    response = client.get(
        f"/api/reconciliation/runs/{run['id']}", headers=auth["finance"]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["id"] == run["id"]
    assert body["results"]["total"] == 2
    assert all(row["run_id"] == run["id"] for row in body["results"]["rows"])


def test_run_detail_returns_404_for_an_unknown_run(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    assert client.get("/api/reconciliation/runs/9999", headers=auth["finance"]).status_code == 404


def test_default_reads_show_the_latest_run(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    first = client.post("/api/reconciliation/run", headers=auth["finance"]).json()
    second = client.post("/api/reconciliation/run", headers=auth["finance"]).json()

    listing = client.get("/api/reconciliation", headers=auth["finance"]).json()
    summary = client.get("/api/reconciliation/summary", headers=auth["finance"]).json()

    # The current view is the second run's, not a doubled set across both runs.
    assert listing["total"] == 2
    assert all(row["run_id"] == second["id"] for row in listing["rows"])
    assert summary["run_id"] == second["id"]
    assert summary["total"] == 2
    assert first["id"] != second["id"]


def test_list_can_be_filtered_to_a_historical_run(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    first = client.post("/api/reconciliation/run", headers=auth["finance"]).json()
    client.post("/api/reconciliation/run", headers=auth["finance"])

    body = client.get(
        f"/api/reconciliation?run_id={first['id']}", headers=auth["finance"]
    ).json()

    assert body["total"] == 2
    assert all(row["run_id"] == first["id"] for row in body["rows"])
    assert all(row["is_current"] is False for row in body["rows"])


def test_summary_can_be_filtered_to_a_historical_run(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory: sessionmaker[Session]
) -> None:
    _seed(session_factory)
    first = client.post("/api/reconciliation/run", headers=auth["finance"]).json()
    client.post("/api/reconciliation/run", headers=auth["finance"])

    body = client.get(
        f"/api/reconciliation/summary?run_id={first['id']}", headers=auth["finance"]
    ).json()

    assert body["run_id"] == first["id"]
    assert body["total"] == 2
