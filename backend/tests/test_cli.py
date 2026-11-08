"""Tests for the interactive ``create-user`` CLI command.

The CLI is pointed at the same in-memory SQLite database the rest of the suite
uses by swapping ``app.cli.SessionLocal`` for the test session factory, and the
interactive prompts are driven by feeding fixed answers to ``input`` /
``getpass.getpass``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.cli as cli
from app.core.roles import RoleName
from app.core.security import verify_password
from app.models import Role, User

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def cli_env(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Iterator[sessionmaker[Session]]:
    """Point the CLI at the in-memory DB and seed the roles it looks up."""
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    with session_factory() as session:
        session.add_all(
            [
                Role(name=RoleName.FINANCE_EXECUTIVE.value),
                Role(name=RoleName.CO_FOUNDER.value),
            ]
        )
        session.commit()
    yield session_factory


def _feed(monkeypatch: pytest.MonkeyPatch, *, answers=(), secrets=()) -> None:
    """Feed fixed sequences of answers to input() and getpass.getpass()."""
    answer_iter = iter(answers)
    secret_iter = iter(secrets)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answer_iter))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(secret_iter))


def _no_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if any interactive prompt is reached."""
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("unexpected input()"))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": pytest.fail("unexpected getpass()"))


def _get_user(factory: sessionmaker[Session], email: str) -> User | None:
    with factory() as session:
        return session.scalar(select(User).where(User.email == email))


def _user_count(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return session.scalar(select(func.count()).select_from(User)) or 0


# --- Interactive flow ------------------------------------------------------


def test_interactive_prompts_create_user(cli_env, monkeypatch) -> None:
    _feed(
        monkeypatch,
        answers=["Finance.User@Example.com", "1"],
        secrets=[PASSWORD, PASSWORD],
    )

    assert cli.main(["create-user"]) == 0

    user = _get_user(cli_env, "finance.user@example.com")
    assert user is not None
    # Email is normalised to lowercase and a display name is derived from it.
    assert user.full_name == "Finance User"
    assert user.is_active is True
    with cli_env() as session:
        role = session.get(Role, user.role_id)
    assert role is not None and role.name == RoleName.FINANCE_EXECUTIVE.value
    # The password is hashed with Argon2id, never stored in plaintext.
    assert user.password_hash != PASSWORD
    assert verify_password(PASSWORD, user.password_hash) is True


def test_interactive_role_may_be_entered_by_name(cli_env, monkeypatch) -> None:
    _feed(
        monkeypatch,
        answers=["founder@example.com", "co_founder"],
        secrets=[PASSWORD, PASSWORD],
    )

    assert cli.main(["create-user"]) == 0

    user = _get_user(cli_env, "founder@example.com")
    assert user is not None
    with cli_env() as session:
        role = session.get(Role, user.role_id)
    assert role is not None and role.name == RoleName.CO_FOUNDER.value


def test_invalid_role_is_reprompted(cli_env, monkeypatch) -> None:
    _feed(
        monkeypatch,
        answers=["retry@example.com", "bogus", "2"],
        secrets=[PASSWORD, PASSWORD],
    )

    assert cli.main(["create-user"]) == 0

    user = _get_user(cli_env, "retry@example.com")
    assert user is not None
    with cli_env() as session:
        role = session.get(Role, user.role_id)
    assert role is not None and role.name == RoleName.CO_FOUNDER.value


def test_invalid_email_is_reprompted(cli_env, monkeypatch) -> None:
    _feed(
        monkeypatch,
        answers=["not-an-email", "valid@example.com", "1"],
        secrets=[PASSWORD, PASSWORD],
    )

    assert cli.main(["create-user"]) == 0
    assert _get_user(cli_env, "valid@example.com") is not None


def test_password_mismatch_is_reprompted(cli_env, monkeypatch) -> None:
    _feed(
        monkeypatch,
        answers=["mismatch@example.com", "1"],
        secrets=[PASSWORD, "a-different-value", PASSWORD, PASSWORD],
    )

    assert cli.main(["create-user"]) == 0
    user = _get_user(cli_env, "mismatch@example.com")
    assert user is not None
    assert verify_password(PASSWORD, user.password_hash) is True


def test_short_password_is_reprompted(cli_env, monkeypatch) -> None:
    _feed(
        monkeypatch,
        answers=["short@example.com", "1"],
        secrets=["short", PASSWORD, PASSWORD],
    )

    assert cli.main(["create-user"]) == 0
    user = _get_user(cli_env, "short@example.com")
    assert user is not None
    assert verify_password(PASSWORD, user.password_hash) is True


def test_eof_on_prompt_returns_error(cli_env, monkeypatch) -> None:
    def _raise_eof(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise_eof)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": pytest.fail("unexpected getpass()"))

    assert cli.main(["create-user"]) == 1
    assert _user_count(cli_env) == 0


# --- Non-interactive flags -------------------------------------------------


def test_flags_create_user_without_prompting(cli_env, monkeypatch) -> None:
    _no_prompts(monkeypatch)

    assert (
        cli.main(
            [
                "create-user",
                "--email",
                "flag@example.com",
                "--full-name",
                "Flag User",
                "--role",
                "co_founder",
                "--password",
                PASSWORD,
            ]
        )
        == 0
    )

    user = _get_user(cli_env, "flag@example.com")
    assert user is not None
    assert user.full_name == "Flag User"
    assert verify_password(PASSWORD, user.password_hash) is True


def test_full_name_defaults_to_email_when_blank(cli_env, monkeypatch) -> None:
    _no_prompts(monkeypatch)

    assert (
        cli.main(
            [
                "create-user",
                "--email",
                "jane.doe@example.com",
                "--full-name",
                "   ",
                "--role",
                "finance_executive",
                "--password",
                PASSWORD,
            ]
        )
        == 0
    )

    user = _get_user(cli_env, "jane.doe@example.com")
    assert user is not None
    assert user.full_name == "Jane Doe"


# --- Validation ------------------------------------------------------------


def test_duplicate_user_is_rejected(cli_env, monkeypatch) -> None:
    _no_prompts(monkeypatch)

    argv = [
        "create-user",
        "--email",
        "dupe@example.com",
        "--role",
        "finance_executive",
        "--password",
        PASSWORD,
    ]
    assert cli.main(argv) == 0
    assert cli.main(argv) == 1
    assert _user_count(cli_env) == 1


def test_duplicate_email_is_case_insensitive(cli_env, monkeypatch) -> None:
    _no_prompts(monkeypatch)

    assert cli.main(
        ["create-user", "--email", "Person@Example.com", "--role", "finance_executive", "--password", PASSWORD]
    ) == 0
    assert cli.main(
        ["create-user", "--email", "person@example.com", "--role", "finance_executive", "--password", PASSWORD]
    ) == 1
    assert _user_count(cli_env) == 1


def test_unknown_role_flag_is_rejected(cli_env, monkeypatch) -> None:
    _no_prompts(monkeypatch)

    assert (
        cli.main(
            ["create-user", "--email", "x@example.com", "--role", "admin", "--password", PASSWORD]
        )
        == 1
    )
    assert _user_count(cli_env) == 0


def test_invalid_email_flag_is_rejected(cli_env, monkeypatch) -> None:
    _no_prompts(monkeypatch)

    assert (
        cli.main(
            ["create-user", "--email", "nope", "--role", "finance_executive", "--password", PASSWORD]
        )
        == 1
    )
    assert _user_count(cli_env) == 0


def test_short_password_flag_is_rejected(cli_env, monkeypatch) -> None:
    _no_prompts(monkeypatch)

    assert (
        cli.main(
            ["create-user", "--email", "short@example.com", "--role", "finance_executive", "--password", "short"]
        )
        == 1
    )
    assert _user_count(cli_env) == 0


def test_unknown_role_in_database_is_rejected(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A role the CLI accepts but the DB has not seeded must not create a user."""
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    _no_prompts(monkeypatch)
    # No roles seeded: the lookup must fail cleanly.
    assert (
        cli.main(
            ["create-user", "--email", "x@example.com", "--role", "finance_executive", "--password", PASSWORD]
        )
        == 1
    )
    assert _user_count(session_factory) == 0


# --- Parser wiring ---------------------------------------------------------


def test_subcommand_is_required() -> None:
    with pytest.raises(SystemExit):
        cli.main([])
