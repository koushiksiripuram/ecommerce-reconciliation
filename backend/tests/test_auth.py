"""Tests for the authentication API and role-based access control.

The suite runs against in-memory SQLite (shared across threads via StaticPool),
so no PostgreSQL instance is required.
"""

from collections.abc import Callable, Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.api.deps import require_roles
from app.core.config import get_settings
from app.core.roles import RoleName
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Role, User

PASSWORD = "correct-horse-battery-staple"
FINANCE_EMAIL = "finance@example.com"
FOUNDER_EMAIL = "founder@example.com"
INACTIVE_EMAIL = "inactive@example.com"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    # StaticPool keeps every connection on the same in-memory database, which
    # matters because FastAPI runs sync endpoints on a worker thread.
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.drop_all(engine)
    engine.dispose()


def _override_get_db(session_factory: sessionmaker[Session]) -> Callable[[], Iterator[Session]]:
    def override() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    return override


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> dict[str, int]:
    """Insert the two roles and three users (one of them inactive)."""
    with session_factory() as session:
        finance_role = Role(name=RoleName.FINANCE_EXECUTIVE.value, description="Finance")
        founder_role = Role(name=RoleName.CO_FOUNDER.value, description="Co-founder")
        session.add_all([finance_role, founder_role])
        session.flush()

        finance = User(
            email=FINANCE_EMAIL,
            full_name="Finance Executive",
            password_hash=hash_password(PASSWORD),
            role_id=finance_role.id,
        )
        founder = User(
            email=FOUNDER_EMAIL,
            full_name="Co Founder",
            password_hash=hash_password(PASSWORD),
            role_id=founder_role.id,
        )
        inactive = User(
            email=INACTIVE_EMAIL,
            full_name="Disabled User",
            password_hash=hash_password(PASSWORD),
            role_id=finance_role.id,
            is_active=False,
        )
        session.add_all([finance, founder, inactive])
        session.commit()

        return {
            "finance_id": finance.id,
            "founder_id": founder.id,
            "inactive_id": inactive.id,
        }


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = _override_get_db(session_factory)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- Login -----------------------------------------------------------------


def test_login_with_valid_credentials_returns_the_profile(
    client: TestClient, seeded: dict[str, int]
) -> None:
    response = _login(client, FINANCE_EMAIL)

    assert response.status_code == 200
    body = response.json()
    # An exact key set proves no credential field can leak into the response.
    assert set(body) == {"id", "email", "full_name", "is_active", "role"}
    assert set(body["role"]) == {"id", "name"}
    assert body["email"] == FINANCE_EMAIL
    assert body["role"]["name"] == RoleName.FINANCE_EXECUTIVE.value


def test_login_sets_an_httponly_cookie_and_not_a_body_token(
    client: TestClient, seeded: dict[str, int]
) -> None:
    response = _login(client, FINANCE_EMAIL)

    set_cookie = response.headers["set-cookie"]
    assert "httponly" in set_cookie.lower()
    assert settings_cookie_name() in set_cookie
    assert "access_token" not in response.json()


def test_login_is_case_insensitive_for_the_email(
    client: TestClient, seeded: dict[str, int]
) -> None:
    response = _login(client, FINANCE_EMAIL.upper())

    assert response.status_code == 200


def test_login_with_a_wrong_password_is_rejected(
    client: TestClient, seeded: dict[str, int]
) -> None:
    response = _login(client, FINANCE_EMAIL, password="wrong-password")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_with_an_unknown_email_is_rejected(
    client: TestClient, seeded: dict[str, int]
) -> None:
    response = _login(client, "nobody@example.com")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_for_a_disabled_account_is_forbidden(
    client: TestClient, seeded: dict[str, int]
) -> None:
    response = _login(client, INACTIVE_EMAIL)

    assert response.status_code == 403


def test_login_without_a_password_is_a_validation_error(
    client: TestClient, seeded: dict[str, int]
) -> None:
    response = client.post("/api/auth/login", json={"email": FINANCE_EMAIL})

    assert response.status_code == 422


# --- Current user ----------------------------------------------------------


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_returns_the_user_after_login(client: TestClient, seeded: dict[str, int]) -> None:
    _login(client, FOUNDER_EMAIL)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["role"]["name"] == RoleName.CO_FOUNDER.value


def test_me_rejects_a_malformed_token(client: TestClient, seeded: dict[str, int]) -> None:
    client.cookies.set(settings_cookie_name(), "not-a-jwt")

    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_a_token_signed_with_another_secret(
    client: TestClient, seeded: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    client.cookies.set(
        settings_cookie_name(),
        create_access_token(seeded["finance_id"], RoleName.FINANCE_EXECUTIVE.value),
    )
    monkeypatch.setenv("JWT_SECRET_KEY", "a-different-secret-entirely-long-enough-for-hs256")
    get_settings.cache_clear()

    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_an_expired_token(
    client: TestClient, seeded: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "-5")
    get_settings.cache_clear()
    expired = create_access_token(seeded["finance_id"], RoleName.FINANCE_EXECUTIVE.value)

    client.cookies.set(settings_cookie_name(), expired)

    assert client.get("/api/auth/me").status_code == 401


def test_me_accepts_a_bearer_token(client: TestClient, seeded: dict[str, int]) -> None:
    token = create_access_token(seeded["finance_id"], RoleName.FINANCE_EXECUTIVE.value)

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == FINANCE_EMAIL


def test_me_rejects_a_token_for_a_user_that_no_longer_exists(client: TestClient) -> None:
    client.cookies.set(
        settings_cookie_name(),
        create_access_token(999_999, RoleName.FINANCE_EXECUTIVE.value),
    )

    assert client.get("/api/auth/me").status_code == 401


# --- Logout ----------------------------------------------------------------


def test_logout_clears_the_cookie(client: TestClient, seeded: dict[str, int]) -> None:
    _login(client, FINANCE_EMAIL)
    assert client.cookies.get(settings_cookie_name())

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert not client.cookies.get(settings_cookie_name())


# --- Role-based authorisation ----------------------------------------------


def _rbac_app() -> FastAPI:
    """A throwaway app exposing one route per role rule."""
    rbac = FastAPI()

    @rbac.get("/finance-only")
    def finance_only(
        user: Annotated[User, Depends(require_roles(RoleName.FINANCE_EXECUTIVE))],
    ) -> dict[str, str]:
        return {"role": user.role.name}

    @rbac.get("/founder-only")
    def founder_only(
        user: Annotated[User, Depends(require_roles(RoleName.CO_FOUNDER))],
    ) -> dict[str, str]:
        return {"role": user.role.name}

    @rbac.get("/either")
    def either(
        user: Annotated[
            User,
            Depends(
                require_roles(RoleName.FINANCE_EXECUTIVE, RoleName.CO_FOUNDER),
            ),
        ],
    ) -> dict[str, str]:
        return {"role": user.role.name}

    return rbac


@pytest.fixture
def rbac_client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    rbac = _rbac_app()
    rbac.dependency_overrides[get_db] = _override_get_db(session_factory)
    with TestClient(rbac) as test_client:
        yield test_client
    rbac.dependency_overrides.clear()


def _auth_header(user_id: int, role: RoleName) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role.value)}"}


def test_role_routes_require_a_token(rbac_client: TestClient) -> None:
    assert rbac_client.get("/finance-only").status_code == 401


def test_role_routes_reject_an_invalid_token(rbac_client: TestClient) -> None:
    response = rbac_client.get("/finance-only", headers={"Authorization": "Bearer nope"})

    assert response.status_code == 401


def test_finance_executive_can_reach_finance_only_route(
    rbac_client: TestClient, seeded: dict[str, int]
) -> None:
    response = rbac_client.get(
        "/finance-only",
        headers=_auth_header(seeded["finance_id"], RoleName.FINANCE_EXECUTIVE),
    )

    assert response.status_code == 200
    assert response.json() == {"role": RoleName.FINANCE_EXECUTIVE.value}


def test_finance_executive_is_forbidden_from_the_founder_route(
    rbac_client: TestClient, seeded: dict[str, int]
) -> None:
    response = rbac_client.get(
        "/founder-only",
        headers=_auth_header(seeded["finance_id"], RoleName.FINANCE_EXECUTIVE),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


def test_co_founder_can_reach_the_founder_route(
    rbac_client: TestClient, seeded: dict[str, int]
) -> None:
    response = rbac_client.get(
        "/founder-only",
        headers=_auth_header(seeded["founder_id"], RoleName.CO_FOUNDER),
    )

    assert response.status_code == 200


def test_co_founder_is_forbidden_from_the_finance_route(
    rbac_client: TestClient, seeded: dict[str, int]
) -> None:
    response = rbac_client.get(
        "/finance-only",
        headers=_auth_header(seeded["founder_id"], RoleName.CO_FOUNDER),
    )

    assert response.status_code == 403


def test_shared_route_accepts_either_role(
    rbac_client: TestClient, seeded: dict[str, int]
) -> None:
    for user_id, role in (
        (seeded["finance_id"], RoleName.FINANCE_EXECUTIVE),
        (seeded["founder_id"], RoleName.CO_FOUNDER),
    ):
        response = rbac_client.get("/either", headers=_auth_header(user_id, role))
        assert response.status_code == 200, role


def settings_cookie_name() -> str:
    """The configured access-token cookie name."""
    return get_settings().auth_cookie_name
