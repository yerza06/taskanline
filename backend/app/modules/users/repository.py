"""Запросы к таблице `users`. Про HTTP здесь ничего не известно."""

from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InstanceRole
from app.modules.users.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        """Сравнение регистронезависимо: колонка объявлена как CITEXT."""
        user: User | None = await self._session.scalar(select(User).where(User.email == email))
        return user

    async def create(
        self, *, email: str, password_hash: str, full_name: str, role: InstanceRole
    ) -> User:
        user = User(email=email, password_hash=password_hash, full_name=full_name, role=role)
        self._session.add(user)
        await self._session.flush()
        return user

    async def any_user_exists(self) -> bool:
        return bool(await self._session.scalar(select(func.count()).select_from(User)))

    async def lock_bootstrap(self) -> None:
        """Блокировка на время решения «первый ли это пользователь».

        Без неё две одновременные регистрации на пустой базе обе увидят ноль строк
        и обе получат роль superadmin. Блокировка транзакционная — снимается сама.
        """
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('users_bootstrap'))")
        )
