"""Tests for password hashing and JWT helpers."""

import jwt
import pytest

from app.core.config import INSECURE_JWT_SECRET, get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    normalize_email,
    verify_password,
)

PASSWORD = "correct-horse-battery-staple"


# --- Password hashing ------------------------------------------------------


def test_hash_password_uses_argon2id_and_hides_the_plaintext() -> None:
    digest = hash_password(PASSWORD)

    assert digest.startswith("$argon2id$")
    assert PASSWORD not in digest


def test_verify_password_accepts_the_correct_password() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_verify_password_rejects_an_incorrect_password() -> None:
    assert verify_password("not-the-password", hash_password(PASSWORD)) is False


def test_hashing_is_salted_so_equal_passwords_differ() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_password_returns_false_for_a_malformed_hash() -> None:
    # A corrupt row must fail closed instead of raising.
    assert verify_password(PASSWORD, "not-a-real-hash") is False


def test_normalize_email_lowercases_and_trims() -> None:
    assert normalize_email("  Finance@Example.COM ") == "finance@example.com"


# --- Tokens ----------------------------------------------------------------


def test_token_round_trip_preserves_subject_and_role() -> None:
    token = create_access_token(42, "finance_executive")

    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["role"] == "finance_executive"
    assert payload["type"] == "access"
    assert payload["exp"] > payload["iat"]


def test_token_is_rejected_when_signed_with_a_different_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_access_token(1, "co_founder")

    monkeypatch.setenv("JWT_SECRET_KEY", "a-completely-different-secret-long-enough-for-hs256")
    get_settings.cache_clear()

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_expired_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "-5")
    get_settings.cache_clear()

    token = create_access_token(1, "finance_executive")

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_is_rejected() -> None:
    token = create_access_token(1, "finance_executive")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload[:-2]}XY.{signature}"

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered)


def test_development_uses_the_placeholder_secret() -> None:
    assert get_settings().jwt_secret_key == INSECURE_JWT_SECRET
