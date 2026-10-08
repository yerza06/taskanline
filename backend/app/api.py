"""Сборка прикладного API.

Все пути версионированы: `/api/v1`. `/health` остаётся снаружи — это не часть
контракта продукта, а признак живости инстанса.
"""

from fastapi import APIRouter

from app.modules.activities import router as activities_router
from app.modules.auth import router as auth_router
from app.modules.invitations import router as invitations_router
from app.modules.labels import router as labels_router
from app.modules.notifications import router as notifications_router
from app.modules.projects import router as projects_router
from app.modules.states import router as states_router
from app.modules.tasks import router as tasks_router
from app.modules.teams import router as teams_router
from app.modules.users import router as users_router
from app.modules.workspaces import router as workspaces_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router.router)
api_router.include_router(auth_router.tokens_router)
api_router.include_router(users_router.router)
api_router.include_router(notifications_router.router)
api_router.include_router(workspaces_router.router)
api_router.include_router(teams_router.workspace_teams_router)
api_router.include_router(teams_router.router)
api_router.include_router(projects_router.team_projects_router)
api_router.include_router(projects_router.router)
api_router.include_router(states_router.team_states_router)
api_router.include_router(states_router.router)
api_router.include_router(invitations_router.router)
api_router.include_router(labels_router.router)
api_router.include_router(tasks_router.router)
api_router.include_router(activities_router.router)
