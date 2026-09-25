"""Бизнес-правила вокруг пользователя."""

from datetime import UTC, datetime
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
