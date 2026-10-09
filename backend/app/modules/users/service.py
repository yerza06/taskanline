"""Бизнес-правила вокруг пользователя."""

import secrets
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def get_active(self, user_id: UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise ApiError(401, "invalid_token", "Сессия недействительна")
        return user

    async def find(self, user_id: UUID) -> User | None:
        """Без проверки активности: имя пригласившего нужно, даже если он заблокирован."""
        return await self._users.get_by_id(user_id)

    async def find_by_email(self, email: str) -> User | None:
        return await self._users.get_by_email(email)

    async def get_many(self, user_ids: Collection[UUID]) -> Sequence[User]:
        return await self._users.get_many(user_ids)

    async def find_many_by_email(self, emails: Collection[str]) -> Sequence[User]:
        """Сравнение регистронезависимо — колонка CITEXT."""
        return await self._users.get_many_by_email(emails)

    async def update_profile(self, user_id: UUID, data: UserUpdate) -> User:
        user = await self.get_active(user_id)
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(user, field, value)
        if changes:
            # updated_at ведётся приложением, а не триггером: иначе метка начинает
            # меняться от служебных апдейтов и перестаёт означать правку по смыслу.
            user.updated_at = datetime.now(UTC)
        await self._session.commit()
        return user

    # --- Для админ-панели: права проверяет вызывающий -----------------------------

    async def search(self, **filters: Any) -> Sequence[User]:
        return await self._users.search(**filters)

    async def status_counts(self) -> dict[str, int]:
        return await self._users.status_counts()

    async def active_superadmins_locked(self) -> list[UUID]:
        return await self._users.active_superadmins_locked()

    async def anonymize(self, user: User) -> None:
        """Удаление — анонимизация: задачи и комментарии сохраняют автора-заглушку.

        Пароль заменяется случайным хешем, адрес — недоставляемой заглушкой: войти
        под удалённой учётной записью нельзя, а адрес освобождается для новой.
        """
        from app.core.security import hash_password

        now = datetime.now(UTC)
        user.email = f"deleted-{user.id}@deleted.invalid"
        user.full_name = "Удалённый пользователь"
        user.avatar_url = None
        user.password_hash = hash_password(secrets.token_urlsafe(32))
        user.is_active = False
        user.deleted_at = now
        user.updated_at = now
        await self._session.flush()
