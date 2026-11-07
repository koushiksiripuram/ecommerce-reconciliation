"""End-to-end integration review of the reconciliation engine.

These tests drive the *real* HTTP surface end to end against a throwaway
in-memory SQLite database: a partner's CSV is uploaded through the Imports API,
mapped, approved and processed, and the resulting data is then reconciled through
the Reconciliation API. Nothing is seeded through the services directly, so the
whole path from file bytes to a reconciled figure is exercised.
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
    FreightPaymentType,
    FreightRateCard,
    FreightServiceType,
    Role,
    User,
)

PASSWORD = "correct-horse-battery-staple"
AuthHeaders = dict[str, str]

# --- Source files ----------------------------------------------------------

# Natural headers: the importer resolves every required field on its own.
ORDERS_CSV = (
    b"Order ID,Order Date,Order Amount,Order Status,Payment Mode,Courier,Zone,Weight\n"
    b"A-1,2020-01-05,100.00,Delivered,Prepaid,Delhivery,A,1000\n"
    b"A-2,2020-01-06,200.00,Delivered,Prepaid,Delhivery,A,1500\n"
    b"A-3,2020-01-07,300.00,Delivered,COD,Delhivery,B,500\n"
    b"A-4,2999-01-01,400.00,Delivered,Prepaid,Delhivery,A,1000\n"
)

# Partner-flavoured headers: nothing maps automatically, so a human must approve.
SETTLEMENTS_CSV = (
    b"PayoutRef,OrigOrder,NetPayout,PayoutDate,FreightFee,TaxTCS,TaxTDS\n"
    b"T-1,A-1,100.00,2020-01-10,50.00,0,0\n"
    b"T-2,A-2,150.00,2020-01-11,50.00,5.00,5.00\n"
    b"T-2,A-2,150.00,2020-01-11,50.00,5.00,5.00\n"
    b"T-9,GHOST-1,75.00,2020-01-12,0,0,0\n"
)

COD_CSV = (
    b"RemitRef,OrderCode,RemitAmt,RemitDate,CodFreight,TcsAmt,TdsAmt\n"
    b"C-1,A-3,280.00,2020-01-15,80.00,0,0\n"
)

# A later file whose headers happen to match the canonical aliases.
EXTRA_SETTLEMENTS_CSV = (
    b"Transaction ID,Order ID,Settlement Amount,Order Date,Shipping Charge\n"
    b"T-4,A-4,400.00,2999-01-02,50.00\n"
)

SETTLEMENT_MAPPING = {
    "transaction_reference": "PayoutRef",
    "external_order_id": "OrigOrder",
    "settlement_amount": "NetPayout",
    "order_date": "PayoutDate",
    "shipping_charge": "FreightFee",
    "tcs_amount": "TaxTCS",
    "tds_amount": "TaxTDS",
}

COD_MAPPING = {
    "transaction_reference": "RemitRef",
    "external_order_id": "OrderCode",
    "settlement_amount": "RemitAmt",
    "order_date": "RemitDate",
    "shipping_charge": "CodFreight",
    "tcs_amount": "TcsAmt",
    "tds_amount": "TdsAmt",
}


def _money(value: object) -> Decimal:
    """Normalise a serialised amount to a two-decimal Decimal."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


# --- Fixtures --------------------------------------------------------------


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
        session.add_all([finance_role, founder_role])
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
        session.add_all([finance, founder])
        session.commit()

        return {
            "finance": {
                "Authorization": f"Bearer {create_access_token(finance.id, finance_role.name)}"
            },
            "founder": {
                "Authorization": f"Bearer {create_access_token(founder.id, founder_role.name)}"
            },
        }


@pytest.fixture
def rate_cards(session_factory: sessionmaker[Session]) -> None:
    """Reference freight data, loaded out of band (there is no rate-card API)."""
    with session_factory() as session:
        session.add_all(
            [
                _card("Delhivery", "A", FreightServiceType.FORWARD, FreightPaymentType.PREPAID, "0", "2000", "50.00"),
                # A different slab on the same route proves slab selection matters.
                _card("Delhivery", "A", FreightServiceType.FORWARD, FreightPaymentType.PREPAID, "2000", "5000", "999.00"),
                # A prepaid rate that a COD shipment must not pick up.
                _card("Delhivery", "B", FreightServiceType.FORWARD, FreightPaymentType.PREPAID, "0", "2000", "500.00"),
                _card("Delhivery", "B", FreightServiceType.FORWARD, FreightPaymentType.COD, "0", "2000", "50.00"),
            ]
        )
        session.commit()


def _card(courier, zone, service_type, payment_type, min_g, max_g, rate) -> FreightRateCard:
    return FreightRateCard(
        courier=courier,
        zone=zone,
        service_type=service_type,
        payment_type=payment_type,
        min_weight_grams=Decimal(min_g),
        max_weight_grams=Decimal(max_g),
        rate=Decimal(rate),
    )


# --- HTTP helpers ----------------------------------------------------------


def _upload(client, headers, *, source_type, partner, filename, content) -> dict:
    response = client.post(
        "/api/imports",
        data={"source_type": source_type, "partner": partner},
        files={"file": (filename, content, "text/csv")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client, headers, batch_id, mapping, *, save=True) -> dict:
    response = client.put(
        f"/api/imports/{batch_id}/mapping",
        json={"mapping": mapping, "save_for_partner": save},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _process(client, headers, batch_id) -> dict:
    response = client.post(f"/api/imports/{batch_id}/process", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _run(client, headers) -> dict:
    response = client.post("/api/reconciliation/run", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _results(client, headers) -> dict:
    response = client.get(
        "/api/reconciliation", params={"limit": 200}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _by_order(page: dict) -> dict[str, dict]:
    return {row["order"]["external_order_id"]: row for row in page["rows"] if row["order"]}


def _import_core(client, headers) -> dict[str, dict]:
    """Upload, map, approve and process the three core files."""
    orders = _upload(
        client, headers, source_type="orders", partner="amazon",
        filename="orders.csv", content=ORDERS_CSV,
    )
    settlements = _upload(
        client, headers, source_type="settlements", partner="amazon",
        filename="settlements.csv", content=SETTLEMENTS_CSV,
    )
    settlements_approved = _approve(
        client, headers, settlements["id"], SETTLEMENT_MAPPING
    )
    settlements_processed = _process(client, headers, settlements["id"])

    cod = _upload(
        client, headers, source_type="cod_remittances", partner="amazon",
        filename="cod.csv", content=COD_CSV,
    )
    cod_approved = _approve(client, headers, cod["id"], COD_MAPPING)
    cod_processed = _process(client, headers, cod["id"])

    orders_processed = _process(client, headers, orders["id"])

    return {
        "orders": orders,
        "orders_processed": orders_processed,
        "settlements": settlements,
        "settlements_approved": settlements_approved,
        "settlements_processed": settlements_processed,
        "cod": cod,
        "cod_approved": cod_approved,
        "cod_processed": cod_processed,
    }


# --- The review ------------------------------------------------------------


def test_full_workflow_from_upload_to_reconciliation(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory, rate_cards
) -> None:
    headers = auth["finance"]

    imported = _import_core(client, headers)

    # 1-4: a natural-header file is ready immediately; an unfamiliar one is not.
    assert imported["orders"]["status"] == "uploaded"
    assert imported["orders_processed"]["status"] == "completed"
    assert imported["settlements"]["status"] == "mapping_required"
    assert imported["settlements_approved"]["status"] == "uploaded"
    assert imported["settlements_processed"]["status"] == "completed"
    assert imported["cod"]["status"] == "mapping_required"
    assert imported["cod_approved"]["status"] == "uploaded"
    assert imported["cod_processed"]["status"] == "completed"

    # 5: run reconciliation through the real API.
    run = _run(client, headers)
    assert run["results_created"] == 5
    assert run["orders_reconciled"] == 4
    assert run["unmatched_settlements"] == 1
    assert run["by_status"] == {
        "settled": 1,
        "short_paid": 2,
        "unpaid_past_due": 0,
        "pending": 1,
        "missing_in_orders": 1,
    }

    # 6: order-level results and the evidence behind them.
    page = _results(client, headers)
    assert page["total"] == 5
    by_order = _by_order(page)

    a1 = by_order["A-1"]
    assert a1["status"] == "settled"
    assert _money(a1["expected_amount"]) == Decimal("100.00")
    assert _money(a1["actual_amount"]) == Decimal("100.00")
    assert _money(a1["difference_amount"]) == Decimal("0.00")
    # The 0-2000 prepaid slab, not the 2000-5000 slab nor the zone-B card.
    assert _money(a1["expected_freight_amount"]) == Decimal("50.00")
    assert a1["issues"] == []

    a2 = by_order["A-2"]
    assert a2["status"] == "short_paid"
    assert _money(a2["difference_amount"]) == Decimal("50.00")
    assert _money(a2["tcs_amount"]) == Decimal("5.00")
    assert _money(a2["tds_amount"]) == Decimal("5.00")
    # The repeated payout line is flagged and counted only once.
    assert [issue["code"] for issue in a2["issues"]] == ["duplicate_settlement"]
    assert a2["issues"][0]["references"] == ["T-2"]

    a3 = by_order["A-3"]
    assert a3["status"] == "short_paid"
    # COD uses the COD slab; the prepaid zone-B card (500.00) must not apply.
    assert _money(a3["expected_freight_amount"]) == Decimal("50.00")
    assert _money(a3["actual_freight_amount"]) == Decimal("80.00")
    overcharge = next(issue for issue in a3["issues"] if issue["code"] == "freight_overcharged")
    assert _money(overcharge["amount"]) == Decimal("30.00")
    assert overcharge["settlement_record_ids"], "the overcharge must cite its evidence"

    assert by_order["A-4"]["status"] == "pending"

    orphan = next(row for row in page["rows"] if row["order"] is None)
    assert orphan["status"] == "missing_in_orders"
    assert _money(orphan["actual_amount"]) == Decimal("75.00")
    assert [issue["code"] for issue in orphan["issues"]] == ["order_not_found"]
    assert orphan["settlement_record"]["order_reference"] == "GHOST-1"

    # 7: summary totals and revenue leakage.
    summary = client.get("/api/reconciliation/summary", headers=headers).json()
    assert summary["total"] == 5
    assert _money(summary["expected_total"]) == Decimal("1000.00")
    assert _money(summary["actual_total"]) == Decimal("605.00")
    assert _money(summary["difference_total"]) == Decimal("395.00")
    assert _money(summary["tcs_total"]) == Decimal("5.00")
    assert _money(summary["tds_total"]) == Decimal("5.00")
    # A-2's 50 gap less 10 withheld, plus A-3's 20. The pending order and the
    # unmatched receipt are not leakage.
    assert _money(summary["revenue_leakage_total"]) == Decimal("60.00")
    assert _money(summary["freight_overcharge_total"]) == Decimal("30.00")


def test_repeated_runs_and_additional_imports_are_consistent(
    client: TestClient, auth: dict[str, AuthHeaders], session_factory, rate_cards
) -> None:
    headers = auth["finance"]
    _import_core(client, headers)

    first_run = _run(client, headers)
    first_values = _snapshot(_results(client, headers))

    # A second run over unchanged data must reproduce exactly the same figures.
    second_run = _run(client, headers)
    assert second_run["results_created"] == first_run["results_created"] == 5
    assert _results(client, headers)["total"] == 5  # no duplicate result rows
    assert _snapshot(_results(client, headers)) == first_values

    # Importing another file must be picked up without disturbing the rest.
    extra = _upload(
        client, headers, source_type="settlements", partner="amazon",
        filename="extra.csv", content=EXTRA_SETTLEMENTS_CSV,
    )
    assert extra["status"] == "uploaded"
    assert _process(client, headers, extra["id"])["status"] == "completed"

    third_run = _run(client, headers)
    assert third_run["results_created"] == 5

    page = _results(client, headers)
    assert page["total"] == 5
    by_order = _by_order(page)

    # A-4 is now paid; every other line keeps its previous figure.
    assert by_order["A-4"]["status"] == "settled"
    assert _money(by_order["A-4"]["actual_amount"]) == Decimal("400.00")
    for order_id in ("A-1", "A-2", "A-3"):
        assert _snapshot_row(by_order[order_id]) in first_values

    summary = client.get("/api/reconciliation/summary", headers=headers).json()
    assert _money(summary["actual_total"]) == Decimal("1005.00")
    assert _money(summary["revenue_leakage_total"]) == Decimal("60.00")


def test_multiple_partial_settlements_are_summed(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    headers = auth["finance"]
    orders = _upload(
        client, headers, source_type="orders", partner="flipkart", filename="orders.csv",
        content=b"Order ID,Order Date,Order Amount,Order Status\nB-1,2020-01-05,100.00,Delivered\n",
    )
    _process(client, headers, orders["id"])

    for index, (reference, amount, date) in enumerate(
        (("S1", "60.00", "2020-01-10"), ("S2", "40.00", "2020-01-11")), start=1
    ):
        batch = _upload(
            client, headers, source_type="settlements", partner="flipkart",
            filename=f"s{index}.csv",
            content=(
                b"Transaction ID,Order ID,Settlement Amount,Order Date\n"
                + f"{reference},B-1,{amount},{date}\n".encode()
            ),
        )
        _process(client, headers, batch["id"])

    run = _run(client, headers)
    assert run["settlements_matched"] == 2

    row = _by_order(_results(client, headers))["B-1"]
    assert row["status"] == "settled"
    assert _money(row["actual_amount"]) == Decimal("100.00")


# --- Snapshot helpers ------------------------------------------------------


def _snapshot_row(row: dict) -> tuple:
    return (
        row["status"],
        str(row["expected_amount"]),
        str(row["actual_amount"]),
        str(row["difference_amount"]),
        str(row["tcs_amount"]),
        str(row["tds_amount"]),
        [issue["code"] for issue in row["issues"]],
    )


def _snapshot(page: dict) -> list[tuple]:
    return sorted(_snapshot_row(row) for row in page["rows"])
