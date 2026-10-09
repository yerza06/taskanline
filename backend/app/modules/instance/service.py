"""Политика инстанса в действии: кто может зарегистрироваться и кто работает во время
обслуживания. Менять её — дело админ-панели (`modules/admin`)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InstanceRole, RegistrationMode
from app.core.errors import ApiError
from app.modules.instance.models import InstanceSettings
from app.modules.instance.repository import InstanceSettingsRepository


def _closed(details: dict[str, object] | None = None) -> ApiError:
    return ApiError(
        403,
        "registration_closed",
        "Самостоятельная регистрация закрыта — нужен инвайт",
        details or {},
    )


class InstanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._settings = InstanceSettingsRepository(session)

    async def get(self) -> InstanceSettings:
        return await self._settings.get()

    async def check_registration(self, email: str) -> None:
        """Можно ли зарегистрироваться без приглашения. Домен сравнивается целиком:
        `mail.acme.com` — не `acme.com`."""
        settings = await self.get()
        match settings.registration_mode:
            case RegistrationMode.OPEN:
                return
            case RegistrationMode.DOMAIN_ALLOWLIST:
                domain = email.rsplit("@", 1)[-1].lower()
                allowed = [item.lower() for item in settings.allowed_email_domains]
                if domain not in allowed:
                    raise _closed({"allowed_domains": allowed})
            case _:
                raise _closed()

    async def check_maintenance(self, role: InstanceRole) -> None:
        """Во время обслуживания работают только роли инстанса — чинить сервер кому-то нужно."""
        if role == InstanceRole.USER and (await self.get()).maintenance_mode:
            raise ApiError(503, "maintenance", "Сервер на обслуживании, попробуйте позже")
