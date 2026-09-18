"""Примитивы аутентификации: пароли, access-токен и токены агентов.

Три разных механизма с разной ценой проверки, и разница здесь не случайна.
Пароль хешируется argon2id — медленно и намеренно. Токен агента хешируется
SHA-256: у него 256 бит энтропии, словарный перебор к нему неприменим, а argon2
на каждом запросе агента добавил бы десятки миллисекунд к каждому вызову.
Access-токен вообще не хранится — он подписан и проверяется по подписи.
"""

import hashlib
import secrets
import string
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from uuid6 import uuid7

from app.core.config import get_settings
from app.core.errors import ApiError

_hasher = PasswordHasher()  # argon2-cffi по умолчанию использует argon2id
_ALPHABET = string.digits + string.ascii_letters

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"

# 32 байта в base62 занимают 43 символа; префикс `tkl_` доводит длину до 47.
_TOKEN_BYTES = 32
_TOKEN_LENGTH = 43
PAT_PREFIX = "tkl_"
PREFIX_LENGTH = 12


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Проверка без исключений наружу: неверный пароль — обычный ответ, не сбой."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def issue_access_token(user_id: UUID, *, now: datetime | None = None) -> str:
    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=settings.auth.access_ttl_minutes)).timestamp()),
        "jti": uuid7().hex,
    }
    return jwt.encode(payload, settings.security.secret_key.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> UUID:
    """Идентификатор владельца токена либо `ApiError(401)`.

    Причина отказа наружу не уточняется: клиенту в любом случае нужно обновить
    сессию, а подробности подсказывают подбирающему, насколько он близок.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.security.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
        )
        if payload.get("typ") != ACCESS_TOKEN_TYPE:
            raise ValueError("не access-токен")
        return UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as error:
        raise ApiError(401, "invalid_token", "Сессия недействительна") from error


def _base62(raw: bytes, length: int) -> str:
    number = int.from_bytes(raw, "big")
    chars: list[str] = []
    while number:
        number, remainder = divmod(number, 62)
        chars.append(_ALPHABET[remainder])
    return "".join(reversed(chars)).rjust(length, _ALPHABET[0])


def generate_pat() -> str:
    """Токен агента. Показывается один раз при создании, в базе живёт только хеш."""
    return f"{PAT_PREFIX}{_base62(secrets.token_bytes(_TOKEN_BYTES), _TOKEN_LENGTH)}"


def generate_refresh_token() -> str:
    """Refresh-токен непрозрачный, а не JWT: его нужно уметь отзывать поимённо."""
    return _base62(secrets.token_bytes(_TOKEN_BYTES), _TOKEN_LENGTH)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_prefix(token: str) -> str:
    """Начало токена для показа в списке: `tkl_7fa3b2c1`."""
    return token[:PREFIX_LENGTH]
