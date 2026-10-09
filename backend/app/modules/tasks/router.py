"""HTTP-слой задач.

`{task_id}` в пути — UUID или ключ `ENG-142` в любом регистре. Неоднозначный ключ
уточняется query-параметром `workspace_id`.
"""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.enums import StateType
from app.core.errors import ApiError
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.core.permissions import AccessContext, Permission, require_permission, resolve_access
from app.core.principal import CurrentPrincipal
from app.modules.idempotency.service import IdempotencyService
from app.modules.tasks.repository import TaskFilters
from app.modules.tasks.schemas import (
    RelationCreate,
    RelationRead,
    TaskCreate,
    TaskLabelsUpdate,
    TaskList,
    TaskMove,
    TaskPage,
    TaskRead,
    TaskUpdate,
)
from app.modules.tasks.service import TaskService, parse_expand

router = APIRouter(prefix="/tasks", tags=["tasks"])

Session = Annotated[AsyncSession, Depends(get_session)]


def get_task_service(session: Session) -> TaskService:
    return TaskService(session)


Service = Annotated[TaskService, Depends(get_task_service)]


def _can(permission: Permission) -> Any:
    return Depends(require_permission(permission, on="task"))


CanRead = Annotated[AccessContext, _can(Permission.TASK_READ)]
CanUpdate = Annotated[AccessContext, _can(Permission.TASK_UPDATE)]
CanDelete = Annotated[AccessContext, _can(Permission.TASK_DELETE)]
CanRestore = Annotated[AccessContext, _can(Permission.TASK_RESTORE)]

TaskId = Annotated[str, "UUID или ключ задачи, например ENG-142"]
Expand = Annotated[
    str | None,
    Query(description="Через запятую: assignee, creator, state, labels, project, parent"),
]
WorkspaceHint = Annotated[
    UUID | None, Query(description="Уточняет ключ задачи, найденный в нескольких workspace")
]


def _people(values: list[str] | None, me: UUID, *, allow_none: bool) -> tuple[list[UUID], bool]:
    """`me`, `none` и UUID в одном фильтре; мусор — `400 invalid_filter`."""
    ids: list[UUID] = []
    empty = False
    for value in values or []:
        if value == "me":
            ids.append(me)
        elif value == "none" and allow_none:
            empty = True
        else:
            try:
                ids.append(UUID(value))
            except ValueError:
                raise ApiError(
                    400,
                    "invalid_filter",
                    "Ожидался UUID, me" + (" или none" if allow_none else ""),
                    {"value": value},
                ) from None
    return ids, empty


@router.get("", response_model=TaskPage, response_model_exclude_unset=True)
async def list_tasks(
    principal: CurrentPrincipal,
    session: Session,
    service: Service,
    workspace_id: Annotated[UUID, Query()],
    team_id: Annotated[list[UUID] | None, Query()] = None,
    project_id: Annotated[list[UUID] | None, Query()] = None,
    state_id: Annotated[list[UUID] | None, Query()] = None,
    state_type: Annotated[list[StateType] | None, Query()] = None,
    assignee_id: Annotated[
        list[str] | None, Query(description="UUID, me или none — без исполнителя")
    ] = None,
    creator_id: Annotated[list[str] | None, Query(description="UUID или me")] = None,
    label_id: Annotated[list[UUID] | None, Query()] = None,
    priority: Annotated[list[int] | None, Query()] = None,
    parent_id: Annotated[list[UUID] | None, Query()] = None,
    due_before: Annotated[date | None, Query()] = None,
    due_after: Annotated[date | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200, description="Полнотекстовый поиск")] = None,
    deleted: Annotated[bool, Query(description="Только удалённые")] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
    expand: Expand = None,
) -> TaskPage:
    ctx = await resolve_access(
        session,
        principal,
        on="workspace",
        object_id=workspace_id,
        permission=Permission.WORKSPACE_READ,
    )
    assignees, unassigned = _people(assignee_id, principal.user_id, allow_none=True)
    creators, _ = _people(creator_id, principal.user_id, allow_none=False)
    if any(value not in range(5) for value in priority or []):
        raise ApiError(400, "invalid_filter", "Приоритет — число от 0 до 4", {"priority": priority})
    filters = TaskFilters(
        team_ids=team_id or (),
        project_ids=project_id or (),
        state_ids=state_id or (),
        state_types=state_type or (),
        assignee_ids=assignees,
        unassigned=unassigned,
        creator_ids=creators,
        label_ids=label_id or (),
        priorities=priority or (),
        parent_ids=parent_id or (),
        due_before=due_before,
        due_after=due_after,
        query=q.strip() if q and q.strip() else None,
        deleted=deleted,
    )
    return await service.list_tasks(
        ctx, filters, limit=limit, cursor=cursor, expand=parse_expand(expand, detail=False)
    )


@router.post(
    "",
    response_model=TaskRead,
    status_code=201,
    response_model_exclude_unset=True,
    responses={201: {"headers": {"Idempotent-Replayed": {"description": "true при повторе"}}}},
)
async def create_task(
    payload: TaskCreate,
    principal: CurrentPrincipal,
    session: Session,
    service: Service,
    expand: Expand = None,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Повтор с тем же ключом и телом вернёт сохранённый ответ",
        ),
    ] = None,
) -> JSONResponse:
    ctx = await resolve_access(
        session,
        principal,
        on="project" if payload.project_id else "team",
        object_id=payload.project_id or payload.team_id,
        permission=Permission.TASK_CREATE,
    )
    fields = parse_expand(expand, detail=True)

    async def produce() -> tuple[int, dict[str, Any]]:
        task = await service.create(ctx, payload)
        (read,) = await service.present(ctx, [task], fields)
        return 201, read.model_dump(mode="json", exclude_unset=True)

    outcome = await IdempotencyService(session).execute(
        user_id=principal.user_id,
        key=idempotency_key,
        endpoint="POST /tasks",
        request={"body": payload.model_dump(mode="json"), "expand": sorted(fields)},
        produce=produce,
    )
    headers = {"Idempotent-Replayed": "true"} if outcome.replayed else None
    return JSONResponse(outcome.body, status_code=outcome.status, headers=headers)


@router.get("/{task_id}", response_model=TaskRead, response_model_exclude_unset=True)
async def read_task(
    task_id: TaskId,
    ctx: CanRead,
    service: Service,
    workspace_id: WorkspaceHint = None,
    expand: Expand = None,
) -> TaskRead:
    task = await service.get(ctx)
    (read,) = await service.present(ctx, [task], parse_expand(expand, detail=True))
    return read


@router.patch("/{task_id}", response_model=TaskRead, response_model_exclude_unset=True)
async def update_task(
    task_id: TaskId,
    payload: TaskUpdate,
    ctx: CanUpdate,
    service: Service,
    workspace_id: WorkspaceHint = None,
    expand: Expand = None,
) -> TaskRead:
    task = await service.update(ctx, payload)
    (read,) = await service.present(ctx, [task], parse_expand(expand, detail=True))
    return read


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: TaskId, ctx: CanDelete, service: Service, workspace_id: WorkspaceHint = None
) -> None:
    await service.delete(ctx)


@router.post("/{task_id}/restore", response_model=TaskRead, response_model_exclude_unset=True)
async def restore_task(
    task_id: TaskId, ctx: CanRestore, service: Service, workspace_id: WorkspaceHint = None
) -> TaskRead:
    (read,) = await service.present(ctx, [await service.restore(ctx)])
    return read


@router.post("/{task_id}/move", response_model=TaskRead, response_model_exclude_unset=True)
async def move_task(
    task_id: TaskId,
    payload: TaskMove,
    ctx: CanUpdate,
    service: Service,
    workspace_id: WorkspaceHint = None,
) -> TaskRead:
    (read,) = await service.present(ctx, [await service.move(ctx, payload)])
    return read


@router.get("/{task_id}/subtasks", response_model=TaskList, response_model_exclude_unset=True)
async def list_subtasks(
    task_id: TaskId,
    ctx: CanRead,
    service: Service,
    workspace_id: WorkspaceHint = None,
    expand: Expand = None,
) -> TaskList:
    return TaskList(items=await service.subtasks(ctx, parse_expand(expand, detail=False)))


@router.post("/{task_id}/relations", response_model=RelationRead, status_code=201)
async def add_relation(
    task_id: TaskId,
    payload: RelationCreate,
    ctx: CanUpdate,
    service: Service,
    workspace_id: WorkspaceHint = None,
) -> RelationRead:
    return await service.add_relation(ctx, payload)


@router.delete("/{task_id}/relations/{relation_id}", status_code=204)
async def remove_relation(
    task_id: TaskId,
    relation_id: UUID,
    ctx: CanUpdate,
    service: Service,
    workspace_id: WorkspaceHint = None,
) -> None:
    await service.remove_relation(ctx, relation_id)


@router.put("/{task_id}/labels", response_model=TaskRead, response_model_exclude_unset=True)
async def replace_labels(
    task_id: TaskId,
    payload: TaskLabelsUpdate,
    ctx: CanUpdate,
    service: Service,
    workspace_id: WorkspaceHint = None,
) -> TaskRead:
    task = await service.set_labels(ctx, payload.label_ids)
    (read,) = await service.present(ctx, [task], {"labels"})
    return read
