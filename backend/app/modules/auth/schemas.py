"""Граница контракта модуля auth."""

from pydantic import BaseModel

from app.modules.users.schemas import UserRead


class SessionResponse(BaseModel):
    """Ответ регистрации, входа и обновления сессии.

    Токены в теле не отдаются: они уходят в httpOnly-cookie и до JavaScript на
    странице не доходят. Клиенту остаётся то, что ему действительно нужно, —
    кто он теперь.
    """

    user: UserRead
