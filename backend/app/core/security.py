"""Password hashing and JWT helpers.

Passwords are hashed with Argon2id (via ``argon2-cffi``) and are never stored,
logged or returned in plaintext. Access tokens are signed JWTs whose claims
carry only the user id and role name — no personal data.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

# A single, process-wide hasher. Argon2 salts each hash individually, so equal
# passwords produce different digests.
_password_hasher = PasswordHasher()

# Verified against when the account does not exist, so that a missing user and
# a wrong password take a comparable amount of time (limits user enumeration).
_DUMMY_HASH = _password_hasher.hash("dummy-password-for-timing-equalisation")


def hash_password(password: str) -> str:
    """Return an Argon2id hash for ``password``."""
    return _password_hasher.hash(password)


def normalize_email(email: str) -> str:
    """Normalise an email address for storage and lookup.

    Stored addresses are always lowercase, so the unique index on ``users.email``
    also behaves as a case-insensitive constraint.
    """
    return email.strip().lower()


def verify_password(password: str, password_hash: str) -> bool:
    """Return ``True`` when ``password`` matches ``password_hash``.

    Any malformed or unreadable hash is treated as a failed verification rather
    than raising, so a corrupt row cannot be turned into an error oracle.
    """
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_password_dummy(password: str) -> None:
    """Burn roughly the same time as a real verification (timing equalisation)."""
    try:
        _password_hasher.verify(_DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass


def create_access_token(subject: str | int, role: str) -> str:
    """Create a signed access token for a user.

    ``subject`` is the user id and ``role`` is the role name; both are claims so
    the API can authorise a request without an extra database round trip.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a token.

    Raises ``jwt.InvalidTokenError`` (which ``ExpiredSignatureError`` subclasses)
    when the token is malformed, expired or signed with the wrong key.
    """
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
