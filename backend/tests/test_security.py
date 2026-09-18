"""Примитивы аутентификации: пароли, access-токен и токены агентов.

База здесь не нужна — это чистые функции, и они должны проверяться без неё.
"""

import hashlib
import string
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from uuid6 import uuid7

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import (
    decode_access_token,
    generate_pat,
    generate_refresh_token,
    hash_password,
    hash_token,
    issue_access_token,
    token_prefix,
    verify_password,
)


class TestPasswords:
    def test_hash_is_argon2id_and_verifies(self) -> None:
        digest = hash_password("correct horse battery staple")

        assert digest.startswith("$argon2id$")
        assert verify_password(digest, "correct horse battery staple") is True

    def test_hash_is_salted(self) -> None:
        """Одинаковые пароли обязаны давать разные хеши, иначе видно совпадения."""
        assert hash_password("same") != hash_password("same")

    def test_wrong_password_is_rejected(self) -> None:
        digest = hash_password("secret")

        assert verify_password(digest, "other") is False

    def test_garbage_hash_does_not_raise(self) -> None:
        """Мусор в колонке не должен ронять запрос пятисоткой."""
        assert verify_password("not-a-hash", "secret") is False


class TestAccessToken:
    def test_roundtrip(self) -> None:
        user_id = uuid7()

        assert decode_access_token(issue_access_token(user_id)) == user_id

    def test_expired_token_is_rejected(self) -> None:
        issued_long_ago = datetime.now(UTC) - timedelta(hours=1)

        token = issue_access_token(uuid7(), now=issued_long_ago)

        with pytest.raises(ApiError) as error:
            decode_access_token(token)
        assert error.value.status_code == 401
        assert error.value.code == "invalid_token"

    def test_token_signed_with_other_key_is_rejected(self) -> None:
        alien = jwt.encode(
            {
                "sub": str(uuid7()),
                "typ": "access",
                "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
            },
            "another-secret-key-at-least-32-characters",
            algorithm="HS256",
        )

        with pytest.raises(ApiError):
            decode_access_token(alien)

    def test_token_of_another_type_is_rejected(self) -> None:
        """typ разделяет назначения: иначе чужой подписанный токен открывает API."""
        payload = {
            "sub": str(uuid7()),
            "typ": "refresh",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        }
        token = jwt.encode(
            payload,
            get_settings().security.secret_key.get_secret_value(),
            algorithm="HS256",
        )

        with pytest.raises(ApiError):
            decode_access_token(token)

    def test_token_with_broken_subject_is_rejected(self) -> None:
        payload = {
            "sub": "не uuid",
            "typ": "access",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        }
        token = jwt.encode(
            payload,
            get_settings().security.secret_key.get_secret_value(),
            algorithm="HS256",
        )

        with pytest.raises(ApiError):
            decode_access_token(token)

    def test_garbage_is_rejected(self) -> None:
        with pytest.raises(ApiError):
            decode_access_token("вообще не токен")


class TestOpaqueTokens:
    def test_pat_shape(self) -> None:
        token = generate_pat()

        assert token.startswith("tkl_")
        assert len(token) == 47
        assert set(token[4:]) <= set(string.digits + string.ascii_letters)

    def test_pat_is_unique(self) -> None:
        assert generate_pat() != generate_pat()

    def test_refresh_token_has_no_prefix_and_is_unique(self) -> None:
        token = generate_refresh_token()

        assert len(token) == 43
        assert not token.startswith("tkl_")
        assert token != generate_refresh_token()

    def test_hash_is_sha256_hex(self) -> None:
        assert hash_token("tkl_x") == hashlib.sha256(b"tkl_x").hexdigest()
        assert len(hash_token("tkl_x")) == 64

    def test_prefix_fits_column(self) -> None:
        """Колонка prefix — VARCHAR(12), и значение обязано в неё помещаться."""
        assert len(token_prefix(generate_pat())) == 12
