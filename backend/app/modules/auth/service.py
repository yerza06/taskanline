"""Сессия человека: регистрация, вход, ротация и выход.

Сервис работает со своими репозиториями и с сервисом users, но никогда — с чужим
репозиторием напрямую.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import InstanceRole
from app.core.errors import ApiError
from app.core.security import (
    generate_refresh_token,
    hash_password,
    hash_token,
    issue_access_token,
    verify_password,
)
from app.modules.auth.repository import RefreshTokenRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import LoginRequest, RegisterRequest

# Хеш заведомо недостижимого пароля. Нужен, чтобы неудачный вход стоил столько же
# времени, сколько удачный: иначе по длительности ответа видно, есть ли такой email.
_DUMMY_HASH = hash_password("нет такого пользователя")


class SessionTokens:
    """Пара токенов, которую роутер кладёт в cookie."""

    def __init__(self, access: str, refresh: str) -> None:
        self.access = access
        self.refresh = refresh


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)

    async def register(
        self, data: RegisterRequest, *, user_agent: str | None, ip: str | None
    ) -> tuple[User, SessionTokens]:
        user, tokens = await self.create_account(data, user_agent=user_agent, ip=ip)
        await self._session.commit()
        return user, tokens

    async def create_account(
        self, data: RegisterRequest, *, user_agent: str | None, ip: str | None
    ) -> tuple[User, SessionTokens]:
        """Регистрация без фиксации: вызывающий дописывает своё и коммитит одной транзакцией.

        Так принятие приглашения не оставит учётную запись без членства, если
        выдача членства сорвётся.
        """
        await self._users.lock_bootstrap()
        # Первому зарегистрировавшемуся нужна роль superadmin: иначе развёрнутым
        # инстансом некому управлять.
        role = InstanceRole.USER if await self._users.any_user_exists() else InstanceRole.SUPERADMIN

        try:
            user = await self._users.create(
                email=data.email,
                password_hash=hash_password(data.password),
                full_name=data.full_name,
                role=role,
            )
        except IntegrityError as error:
            await self._session.rollback()
            raise ApiError(
                409, "email_already_registered", "Этот адрес уже зарегистрирован"
            ) from error

        tokens = await self._issue_session(user, user_agent=user_agent, ip=ip)
        return user, tokens

    async def login(
        self, data: LoginRequest, *, user_agent: str | None, ip: str | None
    ) -> tuple[User, SessionTokens]:
        user = await self._users.get_by_email(data.email)
        # Проверка выполняется даже когда пользователя нет: ответ и его задержка
        # не должны отличать «нет такого адреса» от «неверный пароль».
        password_hash = user.password_hash if user is not None else _DUMMY_HASH
        password_matches = verify_password(password_hash, data.password)

        if user is None or not password_matches or not user.is_active:
            raise ApiError(401, "invalid_credentials", "Неверный адрес или пароль")

        user.last_seen_at = datetime.now(UTC)
        tokens = await self._issue_session(user, user_agent=user_agent, ip=ip)
        await self._session.commit()
        return user, tokens

    async def _issue_session(
        self, user: User, *, user_agent: str | None, ip: str | None
    ) -> SessionTokens:
        settings = get_settings()
        refresh = generate_refresh_token()
        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.auth.refresh_ttl_days),
            user_agent=user_agent,
            ip=ip,
        )
        return SessionTokens(access=issue_access_token(user.id), refresh=refresh)

    async def refresh(
        self, raw_token: str | None, *, user_agent: str | None, ip: str | None
    ) -> tuple[User, SessionTokens]:
        """Ротация: старый токен отзывается, выдаётся новый.

        Повторное использование уже отозванного токена означает, что он утёк:
        либо им воспользовался чужой, либо законный владелец идёт следом. Различить
        эти случаи нельзя, поэтому отзываются все сессии пользователя разом.
        """
        if not raw_token:
            raise ApiError(401, "invalid_token", "Сессия недействительна")

        stored = await self._refresh_tokens.get_by_hash(hash_token(raw_token))
        if stored is None:
            raise ApiError(401, "invalid_token", "Сессия недействительна")

        now = datetime.now(UTC)
        if stored.revoked_at is not None:
            await self._refresh_tokens.revoke_all_for_user(stored.user_id, at=now)
            await self._session.commit()
            raise ApiError(401, "token_reuse_detected", "Обнаружено повторное использование токена")

        if stored.expires_at <= now:
            raise ApiError(401, "invalid_token", "Сессия недействительна")

        user = await self._users.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise ApiError(401, "invalid_token", "Сессия недействительна")

        await self._refresh_tokens.revoke(stored, at=now)
        tokens = await self._issue_session(user, user_agent=user_agent, ip=ip)
        await self._session.commit()
        return user, tokens

    async def logout(self, raw_token: str | None) -> None:
        """Выход без действующей сессии — не ошибка: результат тот же, что просили."""
        if not raw_token:
            return

        stored = await self._refresh_tokens.get_by_hash(hash_token(raw_token))
        if stored is not None and stored.revoked_at is None:
            await self._refresh_tokens.revoke(stored, at=datetime.now(UTC))
            await self._session.commit()
