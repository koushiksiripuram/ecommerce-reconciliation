"""End-to-end tests for the imports API.

A real ``TestClient`` drives the app against in-memory SQLite with the database
dependency overridden, so authentication, role checks, HTTP status mapping and
the full upload -> map -> process workflow are all exercised.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import RoleName
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import Role, User

PASSWORD = "correct-horse-battery-staple"

READY_CSV = b"Order ID,Order Date,Order Amount\nA-1,2026-01-05,100.00\n"
UNMAPPED_CSV = b"ColX,ColY,ColZ\n1,2,3\n"
MIXED_CSV = (
    b"Order ID,Order Date,Order Amount\n"
    b'A-1,2026-01-05,"1,234.56"\n'
    b"A-2,2026-01-06,N/A\n"
)

AuthHeaders = dict[str, str]


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
    """Seed roles/users and return ready-to-use bearer headers per persona."""
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

        def headers(user: User, role_name: str) -> AuthHeaders:
            return {"Authorization": f"Bearer {create_access_token(user.id, role_name)}"}

        return {
            "finance": headers(finance, finance_role.name),
            "founder": headers(founder, founder_role.name),
            "auditor": headers(auditor, auditor_role.name),
        }


def _upload(
    client: TestClient,
    headers: AuthHeaders,
    *,
    content: bytes = READY_CSV,
    filename: str = "orders.csv",
    source_type: str = "orders",
    partner: str = "amazon",
):
    return client.post(
        "/api/imports",
        headers=headers,
        data={"source_type": source_type, "partner": partner},
        files={"file": (filename, content, "text/csv")},
    )


# --- permissions -----------------------------------------------------------


def test_source_types_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/imports/source-types").status_code == 401


def test_source_types_lists_the_supported_types(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    response = client.get("/api/imports/source-types", headers=auth["finance"])

    assert response.status_code == 200
    assert {item["value"] for item in response.json()} == {
        "orders",
        "settlements",
        "cod_remittances",
        "freight_invoices",
        "returns",
    }


def test_upload_requires_authentication(client: TestClient) -> None:
    assert _upload(client, {}).status_code == 401


def test_upload_is_forbidden_for_an_unprivileged_role(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    assert _upload(client, auth["auditor"]).status_code == 403


def test_upload_is_allowed_for_each_finance_role(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    assert _upload(client, auth["finance"]).status_code == 201
    assert _upload(client, auth["founder"], partner="flipkart").status_code == 201


# --- upload validation -----------------------------------------------------


def test_upload_rejects_an_unsupported_extension(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    response = _upload(client, auth["finance"], filename="statement.pdf")

    assert response.status_code == 415


def test_upload_rejects_an_empty_file(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    response = _upload(client, auth["finance"], content=b"")

    assert response.status_code == 400


def test_upload_rejects_an_unsupported_source_type(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    response = _upload(client, auth["finance"], source_type="claims")

    assert response.status_code == 422


def test_upload_requires_a_partner(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    response = client.post(
        "/api/imports",
        headers=auth["finance"],
        data={"source_type": "orders"},
        files={"file": ("orders.csv", READY_CSV, "text/csv")},
    )

    assert response.status_code == 422


def test_duplicate_upload_is_rejected_with_the_existing_batch(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    first = _upload(client, auth["finance"]).json()

    response = _upload(client, auth["finance"])

    assert response.status_code == 409
    assert response.json()["detail"]["existing_batch_id"] == first["id"]


def test_upload_returns_a_summary(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    body = _upload(client, auth["finance"]).json()

    assert body["status"] == "uploaded"
    assert body["source_type"] == "orders"
    assert body["source_label"] == "Orders"
    assert body["partner"] == "amazon"
    assert body["total_rows"] == 1
    assert body["original_filename"] == "orders.csv"


def test_upload_leaves_incomplete_files_awaiting_mapping(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    body = _upload(client, auth["finance"], content=UNMAPPED_CSV).json()

    assert body["status"] == "mapping_required"


# --- listing and reads -----------------------------------------------------


def test_list_imports_returns_recent_batches(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    _upload(client, auth["finance"])

    response = client.get("/api/imports", headers=auth["finance"])

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_imports_filters_by_partner(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    _upload(client, auth["finance"], partner="amazon")
    _upload(client, auth["finance"], partner="flipkart")

    response = client.get("/api/imports?partner=amazon", headers=auth["finance"])

    assert response.status_code == 200
    assert [item["partner"] for item in response.json()] == ["amazon"]


def test_list_imports_rejects_a_bad_limit(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    assert client.get("/api/imports?limit=0", headers=auth["finance"]).status_code == 422


def test_get_import_returns_one_batch(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"]).json()["id"]

    response = client.get(f"/api/imports/{batch_id}", headers=auth["finance"])

    assert response.status_code == 200
    assert response.json()["id"] == batch_id


def test_get_import_returns_404_for_an_unknown_batch(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    assert client.get("/api/imports/9999", headers=auth["finance"]).status_code == 404


# --- preview, mapping and processing ---------------------------------------


def test_preview_returns_headers_and_fields(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"]).json()["id"]

    response = client.get(f"/api/imports/{batch_id}/preview", headers=auth["finance"])

    assert response.status_code == 200
    body = response.json()
    assert body["headers"] == ["Order ID", "Order Date", "Order Amount"]
    assert body["mapping_complete"] is True
    assert len(body["rows"]) == 1


def test_mapping_update_is_forbidden_for_an_unprivileged_role(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"], content=UNMAPPED_CSV).json()["id"]

    response = client.put(
        f"/api/imports/{batch_id}/mapping",
        headers=auth["auditor"],
        json={"mapping": {"external_order_id": "ColX"}},
    )

    assert response.status_code == 403


def test_mapping_update_rejects_an_unknown_field(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"], content=UNMAPPED_CSV).json()["id"]

    response = client.put(
        f"/api/imports/{batch_id}/mapping",
        headers=auth["finance"],
        json={"mapping": {"nope": "ColX"}},
    )

    assert response.status_code == 422


def test_mapping_update_completes_the_batch(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"], content=UNMAPPED_CSV).json()["id"]

    response = client.put(
        f"/api/imports/{batch_id}/mapping",
        headers=auth["finance"],
        json={
            "mapping": {
                "external_order_id": "ColX",
                "order_date": "ColY",
                "order_amount": "ColZ",
            },
            "save_for_partner": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"


def test_process_completes_the_batch(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"], content=MIXED_CSV).json()["id"]

    response = client.post(f"/api/imports/{batch_id}/process", headers=auth["finance"])

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["total_rows"] == 2
    assert body["processed_rows"] == 1
    assert body["failed_rows"] == 1


def test_process_is_rejected_for_a_batch_awaiting_mapping(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"], content=UNMAPPED_CSV).json()["id"]

    response = client.post(f"/api/imports/{batch_id}/process", headers=auth["finance"])

    assert response.status_code == 409


def test_mapping_cannot_change_after_processing(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"]).json()["id"]
    client.post(f"/api/imports/{batch_id}/process", headers=auth["finance"])

    response = client.put(
        f"/api/imports/{batch_id}/mapping",
        headers=auth["finance"],
        json={"mapping": {"external_order_id": "Order ID"}},
    )

    assert response.status_code == 409


def test_records_endpoint_pages_through_stored_rows(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"], content=MIXED_CSV).json()["id"]
    client.post(f"/api/imports/{batch_id}/process", headers=auth["finance"])

    response = client.get(f"/api/imports/{batch_id}/records", headers=auth["finance"])

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["returned"] == 2


def test_records_endpoint_can_return_only_invalid_rows(
    client: TestClient, auth: dict[str, AuthHeaders]
) -> None:
    batch_id = _upload(client, auth["finance"], content=MIXED_CSV).json()["id"]
    client.post(f"/api/imports/{batch_id}/process", headers=auth["finance"])

    response = client.get(
        f"/api/imports/{batch_id}/records?only_invalid=true", headers=auth["finance"]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["is_valid"] is False
    assert body["rows"][0]["errors"][0]["code"] == "invalid_amount"
