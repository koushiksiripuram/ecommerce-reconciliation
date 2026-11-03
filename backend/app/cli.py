"""Administrative command-line utilities.

This is the *only* way to create a user: there is no public registration
endpoint, and no credentials are shipped with the application. Run it with the
same environment configuration as the API so it targets the same database.

Examples
--------
::

    python -m app.cli create-user --email finance@example.com \\
        --full-name "Asha Rao" --role finance_executive

The password is prompted for (and confirmed) unless ``--password`` is supplied.
"""

import argparse
import getpass
import sys
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.roles import RoleName, role_names
from app.core.security import hash_password, normalize_email
from app.db.session import SessionLocal
from app.models import Role, User

MIN_PASSWORD_LENGTH = 8


def _prompt_password() -> str:
    """Read a password twice from the terminal without echoing it."""
    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    return password


def create_user(args: argparse.Namespace) -> int:
    """Create a user, hashing the password before it is stored."""
    email = normalize_email(args.email)
    try:
        password = args.password or _prompt_password()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"error: Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 1

    with SessionLocal() as session:
        role = session.scalar(select(Role).where(Role.name == args.role))
        if role is None:
            print(
                f"error: Unknown role {args.role!r}. Run the migrations first; "
                f"known roles: {', '.join(role_names())}.",
                file=sys.stderr,
            )
            return 1

        if session.scalar(select(User).where(User.email == email)) is not None:
            print(f"error: A user with email {email!r} already exists.", file=sys.stderr)
            return 1

        user = User(
            email=email,
            full_name=args.full_name.strip(),
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

    create = subparsers.add_parser("create-user", help="Create a user (prompts for a password).")
    create.add_argument("--email", required=True, help="Unique email address.")
    create.add_argument("--full-name", required=True, help="Display name.")
    create.add_argument(
        "--role",
        required=True,
        choices=role_names(),
        help="Role to grant the user.",
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
