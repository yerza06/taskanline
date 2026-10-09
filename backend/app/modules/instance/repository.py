from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.instance.models import SETTINGS_ID, InstanceSettings


class InstanceSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> InstanceSettings:
        """Строку создаёт миграция; её отсутствие — сломанная база, а не пустые настройки."""
        settings = await self._session.scalar(
            select(InstanceSettings).where(InstanceSettings.id == SETTINGS_ID)
        )
        if settings is None:
            raise RuntimeError("instance_settings пуста: миграция 0006_admin не применена")
        return settings
