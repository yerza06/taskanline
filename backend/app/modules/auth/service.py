"""Сессия человека: регистрация, вход, ротация и выход.

Сервис работает со своими репозиториями и с сервисом users, но никогда — с чужим
репозиторием напрямую.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import InstanceRole, LoginKind
from app.core.errors import ApiError
from app.core.mail import MailMessage
from app.core.security import (
    generate_refresh_token,
    hash_password,
    hash_token,
    issue_access_token,
    verify_password,
)
from app.modules.auth.models import LoginEvent, PasswordResetToken
from app.modules.auth.repository import (
    LoginEventRepository,
    PasswordResetRepository,
    RefreshTokenRepository,
)
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import LoginRequest, RegisterRequest

# Хеш заведомо недостижимого пароля. Нужен, чтобы неудачный вход стоил столько же
# времени, сколько удачный: иначе по длительности ответа видно, есть ли такой email.
_DUMMY_HASH = hash_password("нет такого пользователя")
# Ссылка на смену пароля живёт час: дольше — лишний шанс для того, кто читает чужую почту.
PASSWORD_RESET_TTL = timedelta(hours=1)


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
        self._logins = LoginEventRepository(session)
        self._resets = PasswordResetRepository(session)

    async def register(
        self, data: RegisterRequest, *, user_agent: str | None, ip: str | None
    ) -> tuple[User, SessionTokens]:
        # Импорт внутри: модуль instance зависит от core, а не от auth, но держим
        # верхний уровень auth свободным от чужих модулей, как и в остальных сервисах.
        from app.modules.instance.service import InstanceService

        await self._users.lock_bootstrap()
        # Пустой инстанс открыт всегда: по умолчанию регистрация закрыта, а приглашать
        # ещё некому. Первый зарегистрировавшийся получит superadmin.
        if await self._users.any_user_exists():
            await InstanceService(self._session).check_registration(data.email)
        user, tokens = await self.create_account(data, user_agent=user_agent, ip=ip)
        await self._session.commit()
        return user, tokens

    async def create_account(
        self,
        data: RegisterRequest,
        *,
        user_agent: str | None,
        ip: str | None,
        kind: LoginKind = LoginKind.REGISTRATION,
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
        await self.record_login(user, kind, user_agent=user_agent, ip=ip)
        return user, tokens

    async def record_login(
        self, user: User, kind: LoginKind, *, user_agent: str | None, ip: str | None
    ) -> None:
        """Строка журнала входов — для карточки пользователя в админке. Без commit."""
        await self._logins.add(LoginEvent(user_id=user.id, kind=kind, ip=ip, user_agent=user_agent))

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

        from app.modules.instance.service import InstanceService

        await InstanceService(self._session).check_maintenance(user.role)

        user.last_seen_at = datetime.now(UTC)
        tokens = await self._issue_session(user, user_agent=user_agent, ip=ip)
        await self.record_login(user, LoginKind.PASSWORD, user_agent=user_agent, ip=ip)
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

    # --- Сессии и входы для админ-панели -----------------------------------------

    async def revoke_sessions(self, user_id: UUID) -> None:
        """Все refresh-токены пользователя — разом. Без commit."""
        await self._refresh_tokens.revoke_all_for_user(user_id, at=datetime.now(UTC))

    async def recent_logins(self, user_id: UUID, *, limit: int = 20) -> Sequence[LoginEvent]:
        return await self._logins.recent(user_id, limit=limit)

    # --- Сброс пароля -------------------------------------------------------------

    async def start_password_reset(self, user: User, *, requested_by: UUID | None) -> MailMessage:
        """Новая ссылка на смену пароля; прежние неиспользованные гаснут. Без commit.

        Пароль не показывается никому — ни администратору, запустившему сброс, ни
        в журнале: пароль, который знает кто-то кроме владельца, перестаёт быть
        доказательством личности.
        """
        from app.modules.instance.service import InstanceService

        now = datetime.now(UTC)
        await self._resets.invalidate_unused(user.id, at=now)
        raw = generate_refresh_token()
        await self._resets.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(raw),
                requested_by=requested_by,
                expires_at=now + PASSWORD_RESET_TTL,
            )
        )
        settings = get_settings()
        instance = (await InstanceService(self._session).get()).instance_name
        link = f"{settings.app.public_url.rstrip('/')}/reset-password/{raw}"
        return MailMessage(
            to=user.email,
            subject=f"{instance}: смена пароля",
            body=(
                f"Здравствуйте, {user.full_name}!\n\n"
                f"Чтобы задать новый пароль, откройте ссылку (действует час):\n{link}\n\n"
                "Если вы не просили сменить пароль, просто проигнорируйте это письмо."
            ),
        )

    async def forgot_password(self, email: str) -> MailMessage | None:
        """«Забыл пароль»: письмо уходит, только если адрес есть и учётная запись жива.
        Ответ наружу одинаковый в обоих случаях — перебором адресов ничего не узнать."""
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            return None
        message = await self.start_password_reset(user, requested_by=None)
        await self._session.commit()
        return message

    async def reset_password(
        self, raw_token: str, password: str, *, user_agent: str | None, ip: str | None
    ) -> tuple[User, SessionTokens]:
        """Новый пароль по ссылке: все прежние сессии гаснут, открывается новая."""
        stored = await self._resets.get_by_hash(hash_token(raw_token))
        now = datetime.now(UTC)
        if stored is None or stored.used_at is not None or stored.expires_at <= now:
            raise ApiError(400, "reset_token_invalid", "Ссылка недействительна или устарела")
        user = await self._users.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise ApiError(400, "reset_token_invalid", "Ссылка недействительна или устарела")

        stored.used_at = now
        user.password_hash = hash_password(password)
        user.updated_at = now
        await self._refresh_tokens.revoke_all_for_user(user.id, at=now)
        tokens = await self._issue_session(user, user_agent=user_agent, ip=ip)
        await self.record_login(user, LoginKind.PASSWORD_RESET, user_agent=user_agent, ip=ip)
        await self._session.commit()
        return user, tokens
