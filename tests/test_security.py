"""Unit tests for security utilities."""
from __future__ import annotations

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hash_and_verify() -> None:
    plain = "supersecret"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("wrongpassword", hashed)


def test_access_token_roundtrip() -> None:
    user_id = "abc-123"
    token = create_access_token(subject=user_id)
    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "access"


def test_access_token_with_extra_claims() -> None:
    token = create_access_token(
        subject="user-1",
        extra_claims={"company_id": "co-1", "role": "owner"},
    )
    payload = decode_access_token(token)
    assert payload["company_id"] == "co-1"
    assert payload["role"] == "owner"


def test_decode_invalid_token_raises() -> None:
    with pytest.raises(JWTError):
        decode_access_token("not.a.valid.token")


def test_refresh_token_hash_is_deterministic() -> None:
    raw, h1 = create_refresh_token()
    h2 = hash_token(raw)
    assert h1 == h2


def test_refresh_tokens_are_unique() -> None:
    tokens = {create_refresh_token()[0] for _ in range(10)}
    assert len(tokens) == 10
