"""HTTP-слой views."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.core.principal import CurrentPrincipal
from app.modules.tasks.service import parse_expand
from app.modules.views.models import View
from app.modules.views.schemas import ViewCreate, ViewList, ViewRead, ViewTasks, ViewUpdate
from app.modules.views.service import ViewService

router = APIRouter(prefix="/views", tags=["views"])


def get_view_service(session: Annotated[AsyncSession, Depends(get_session)]) -> ViewService:
    return ViewService(session)


Service = Annotated[ViewService, Depends(get_view_service)]


def _uuid(raw: str) -> UUID | None:
    """Не-UUID в пути — такого view нет (404), а не ошибка формата (422)."""
    try:
        return UUID(raw)
    except ValueError:
        return None


def _read(view: View, can_edit: bool) -> ViewRead:
    return ViewRead(
        id=view.id,
        workspace_id=view.workspace_id,
        scope=view.scope,
        owner_id=view.owner_id,
        team_id=view.team_id,
        name=view.name,
        description=view.description,
        icon=view.icon,
        color=view.color,
        filters=view.filters,
        group_by=view.group_by,
        sort_by=view.sort_by,
        sort_direction=view.sort_direction,
        layout=view.layout,
        position=view.position,
        created_by=view.created_by,
        created_at=view.created_at,
        updated_at=view.updated_at,
        can_edit=can_edit,
    )


@router.get("", response_model=ViewList)
async def list_views(
    principal: CurrentPrincipal, service: Service, workspace_id: Annotated[UUID, Query()]
) -> ViewList:
    """Личные views, views видимых команд и — кроме гостей — общие для workspace."""
    rows = await service.list_visible(principal, workspace_id)
    return ViewList(items=[_read(view, can_edit) for view, can_edit in rows])


@router.post("", response_model=ViewRead, status_code=201)
async def create_view(
    payload: ViewCreate, principal: CurrentPrincipal, service: Service
) -> ViewRead:
    return _read(*await service.create(principal, payload))


@router.get("/{view_id}", response_model=ViewRead)
async def read_view(view_id: str, principal: CurrentPrincipal, service: Service) -> ViewRead:
    return _read(*await service.get(principal, _uuid(view_id)))


@router.patch("/{view_id}", response_model=ViewRead)
async def update_view(
    view_id: str, payload: ViewUpdate, principal: CurrentPrincipal, service: Service
) -> ViewRead:
    return _read(*await service.update(principal, _uuid(view_id), payload))


@router.delete("/{view_id}", status_code=204)
async def delete_view(view_id: str, principal: CurrentPrincipal, service: Service) -> None:
    await service.delete(principal, _uuid(view_id))


@router.get("/{view_id}/tasks", response_model=ViewTasks, response_model_exclude_unset=True)
async def run_view(
    view_id: str,
    principal: CurrentPrincipal,
    service: Service,
    group: Annotated[
        str | None,
        Query(description="Ключ группы — листать одну колонку; none — группа без значения"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Задач на группу")] = (
        DEFAULT_LIMIT
    ),
    cursor: Annotated[str | None, Query()] = None,
    expand: Annotated[str | None, Query(description="Как в GET /tasks")] = None,
) -> ViewTasks:
    """Задачи view: фильтры, видимость читателя, сортировка и группировка view."""
    view, groups = await service.run(
        principal,
        _uuid(view_id),
        group=group,
        cursor=cursor,
        limit=limit,
        expand=parse_expand(expand, detail=False),
    )
    return ViewTasks(view_id=view.id, group_by=view.group_by, groups=groups)
