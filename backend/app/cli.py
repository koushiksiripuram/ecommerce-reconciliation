"""Administrative command-line utilities.

This is the *only* way to create a user: there is no public registration
endpoint, and no credentials are shipped with the application. Run it with the
same environment configuration as the API so it targets the same database.

``create-user`` is interactive by default and prompts for an email, a hidden
password (entered twice) and a role. Every prompt can also be supplied as a flag,
which is what non-interactive environments (CI, provisioning scripts) should do.
Passwords are always hashed with Argon2id before they are stored.

Examples
--------
Interactive::

    python -m app.cli create-user

Non-interactive::

    python -m app.cli create-user --email finance@example.com \\
        --full-name "Asha Rao" --role finance_executive --password "..."
"""

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.roles import RoleName, role_names
from app.core.security import hash_password, normalize_email
from app.db.session import SessionLocal
from app.models import Role, User

MIN_PASSWORD_LENGTH = 8


def _validate_email(value: str) -> str:
    """Normalise and validate an email address.

    Stored addresses are lowercased, so the unique index on ``users.email`` also
    acts as a case-insensitive constraint.
    """
    email = normalize_email(value)
    local, _, domain = email.partition("@")
    if not local or not domain:
        raise ValueError("Enter a valid email address (name@domain).")
    return email


def _validate_role(value: str) -> str:
    """Return a known role name from either a menu index or a role name."""
    names = role_names()
    candidate = value.strip().lower()
    if candidate.isdigit():
        index = int(candidate)
        if 1 <= index <= len(names):
            return names[index - 1]
    if candidate in names:
        return candidate
    raise ValueError(f"Role must be one of: {', '.join(names)}.")


def _validate_password(value: str) -> str:
    """Enforce the minimum password length."""
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return value


def _display_name_from_email(email: str) -> str:
    """Derive a readable display name from the email local part."""
    local = email.partition("@")[0]
    for separator in (".", "_", "-", "+"):
        local = local.replace(separator, " ")
    name = " ".join(part.capitalize() for part in local.split())
    return name or email


def _prompt(label: str, validate: Callable[[str], str]) -> str:
    """Prompt repeatedly until ``validate`` accepts the entered value."""
    while True:
        try:
            raw = input(label)
        except EOFError:
            raise ValueError(
                "No input received. Supply --email/--role/--password for non-interactive use."
            ) from None
        try:
            return validate(raw)
        except ValueError as exc:
            print(f"  {exc}", file=sys.stderr)


def _prompt_password() -> str:
    """Read a hidden password twice, re-prompting on mismatch or weakness."""
    while True:
        try:
            password = getpass.getpass("Password: ")
        except EOFError:
            raise ValueError(
                "No input received. Supply --password for non-interactive use."
            ) from None
        try:
            _validate_password(password)
        except ValueError as exc:
            print(f"  {exc}", file=sys.stderr)
            continue

        try:
            confirmation = getpass.getpass("Confirm password: ")
        except EOFError:
            raise ValueError(
                "No input received. Supply --password for non-interactive use."
            ) from None
        if password != confirmation:
            print("  Passwords do not match.", file=sys.stderr)
            continue
        return password


def create_user(args: argparse.Namespace) -> int:
    """Create a user, hashing the password before it is stored.

    Any value not supplied on the command line is prompted for interactively.
    Returns a process exit code: 0 on success, 1 on any validation or database
    error (so the command is safe to call from a script).
    """
    try:
        email = _validate_email(args.email) if args.email is not None else _prompt(
            "Email: ", _validate_email
        )

        full_name = (args.full_name or "").strip() or _display_name_from_email(email)

        if args.role is not None:
            role_name = _validate_role(args.role)
        else:
            options = ", ".join(
                f"{index}) {name}" for index, name in enumerate(role_names(), start=1)
            )
            print(f"Available roles: {options}")
            role_name = _prompt("Role: ", _validate_role)

        password = args.password if args.password is not None else _prompt_password()
        password = _validate_password(password)
    except (ValueError, KeyboardInterrupt) as exc:
        print(f"error: {str(exc) or 'Cancelled.'}", file=sys.stderr)
        return 1

    with SessionLocal() as session:
        role = session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            print(
                f"error: Unknown role {role_name!r}. Run the migrations first; "
                f"known roles: {', '.join(role_names())}.",
                file=sys.stderr,
            )
            return 1

        if session.scalar(select(User).where(User.email == email)) is not None:
            print(f"error: A user with email {email!r} already exists.", file=sys.stderr)
            return 1

        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role_id=role.id,
        )
        session.add(user)
        try:
            session.commit()
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            session.rollback()
            print(f"error: Could not create the user: {exc}", file=sys.stderr)
            return 1

        print(f"Created user {user.email!r} with role {role.name!r}.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(prog="app.cli", description="Administrative utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create-user",
        help="Create a user (interactive unless every value is supplied as a flag).",
        description=(
            "Create a user. The email, password (hidden, entered twice) and role are "
            "prompted for unless supplied as flags."
        ),
    )
    create.add_argument("--email", default=None, help="Unique email address (prompted if omitted).")
    create.add_argument(
        "--full-name",
        default=None,
        help="Display name. Defaults to a name derived from the email.",
    )
    create.add_argument(
        "--role",
        default=None,
        help=f"Role to grant: {', '.join(role_names())} (prompted if omitted).",
    )
    create.add_argument(
        "--password",
        default=None,
        help="Password. Omit to be prompted; supplying it may leak into shell history.",
    )
    create.set_defaults(func=create_user)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
