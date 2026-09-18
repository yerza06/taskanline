"""Граница контракта модуля auth."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import TokenScope
from app.modules.users.schemas import UserRead


class SessionResponse(BaseModel):
    """Ответ регистрации, входа и обновления сессии.

    Токены в теле не отдаются: они уходят в httpOnly-cookie и до JavaScript на
    странице не доходят. Клиенту остаётся то, что ему действительно нужно, —
    кто он теперь.
    """

    user: UserRead


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope: TokenScope = TokenScope.READ
    expires_at: datetime | None = Field(default=None, description="Пусто — токен бессрочный")


class TokenRead(BaseModel):
    """Вид токена в списке. Полного значения здесь нет и быть не может."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    prefix: str
    scope: TokenScope
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class TokenCreated(TokenRead):
    """Ответ на выпуск: единственный момент, когда виден полный токен."""

    token: str


class TokenList(BaseModel):
    items: list[TokenRead]
