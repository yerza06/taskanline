"""Публичные сведения об инстансе — без аутентификации."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.instance.schemas import InstanceInfo
from app.modules.instance.service import InstanceService

router = APIRouter(prefix="/instance", tags=["instance"])


@router.get("", response_model=InstanceInfo)
async def instance_info(session: Annotated[AsyncSession, Depends(get_session)]) -> InstanceInfo:
    """Название инстанса и режим регистрации — экран регистрации показывает их заранее."""
    settings = await InstanceService(session).get()
    return InstanceInfo(
        instance_name=settings.instance_name, registration_mode=settings.registration_mode
    )
