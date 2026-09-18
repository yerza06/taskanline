"""Сборка прикладного API.

Все пути версионированы: `/api/v1`. `/health` остаётся снаружи — это не часть
контракта продукта, а признак живости инстанса.
"""

from fastapi import APIRouter

from app.modules.auth import router as auth_router
from app.modules.users import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router.router)
api_router.include_router(users_router.router)
