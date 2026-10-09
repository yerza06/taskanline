"""Бизнес-правила задач: создание, изменения, порядок, подзадачи и связи.

Каждое изменение пишет событие в историю той же транзакцией — иначе при сбое история
разойдётся с данными. Создание не коммитит само: его коммитит `IdempotencyService`,
чтобы сохранённый ответ и задача появились или не появились вместе.
"""

from collections.abc import Collection, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CLOSED_STATE_TYPES,
    ActivityType,
    NotificationType,
    RelationType,
    StateType,
    ViewGroupBy,
)
from app.core.errors import ApiError
from app.core.fractional_index import key_between, keys_between
from app.core.pagination import decode_cursor, paginate
from app.core.permissions import (
    AccessContext,
    AccessTarget,
    EffectiveRole,
    Permission,
    compute_effective_role,
    load_access,
    resolve_access,
    task_ref_to_id,
    task_visibility,
)
from app.modules.activities.service import ActivityService
from app.modules.labels.service import LabelService
from app.modules.notifications.service import NotificationService
from app.modules.projects.service import ProjectService
from app.modules.states.models import WorkflowState
from app.modules.states.service import StateService
from app.modules.tasks.models import Task, TaskRelation
from app.modules.tasks.ordering import (
    NO_PRIORITY_RANK,
    SortSpec,
    format_group_key,
    parse_group_key,
)
from app.modules.tasks.repository import TaskFilters, TaskRepository
from app.modules.tasks.schemas import (
    LabelBrief,
    ProjectBrief,
    RelationCreate,
    RelationRead,
    RelationView,
    StateBrief,
    TaskBrief,
    TaskCreate,
    TaskGroup,
    TaskMove,
    TaskPage,
    TaskRead,
    TaskUpdate,
    UserBrief,
)
from app.modules.teams.service import TeamService
from app.modules.users.service import UserService

EXPANDABLE = frozenset({"assignee", "creator", "state", "labels", "project", "parent"})
DETAIL_EXPANDABLE = EXPANDABLE | {"relations"}
# Глубина дерева подзадач, считая корень.
MAX_DEPTH = 5
# Длиннее — ключи всей команды перегенерируются.
MAX_SORT_KEY = 32

# Связь со стороны задачи → (хранимый тип, задача — источник?).
_STORED: dict[str, tuple[RelationType, bool]] = {
    "blocks": (RelationType.BLOCKS, True),
    "blocked_by": (RelationType.BLOCKS, False),
    "relates_to": (RelationType.RELATES_TO, True),
    "duplicates": (RelationType.DUPLICATES, True),
    "duplicated_by": (RelationType.DUPLICATES, False),
}
_FORWARD: dict[RelationType, RelationView] = {
    RelationType.BLOCKS: "blocks",
    RelationType.RELATES_TO: "relates_to",
    RelationType.DUPLICATES: "duplicates",
}
_INVERSE: dict[RelationType, RelationView] = {
    RelationType.BLOCKS: "blocked_by",
    RelationType.RELATES_TO: "relates_to",
    RelationType.DUPLICATES: "duplicated_by",
}


def parse_expand(raw: str | None, *, detail: bool) -> frozenset[str]:
    """`?expand=assignee,labels` → множество; неизвестное значение — `400 invalid_expand`."""
    if not raw:
        return frozenset()
    requested = frozenset(part.strip() for part in raw.split(",") if part.strip())
    allowed = DETAIL_EXPANDABLE if detail else EXPANDABLE
    unknown = requested - allowed
    if unknown:
        raise ApiError(
            400,
            "invalid_expand",
            "Неизвестное значение expand",
            {"unknown": sorted(unknown), "allowed": sorted(allowed)},
        )
    return requested


def _not_found() -> ApiError:
    return ApiError(404, "task_not_found", "Задача не найдена")


def _state_payload(state: WorkflowState) -> dict[str, Any]:
    return {"id": str(state.id), "name": state.name, "type": state.type}


def _id(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _day(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _apply_state(task: Task, state: WorkflowState, now: datetime) -> None:
    """`started_at` — при первом переходе в started; `completed_at` — пока задача закрыта."""
    task.state_id = state.id
    if state.type == StateType.STARTED and task.started_at is None:
        task.started_at = now
    if state.type in CLOSED_STATE_TYPES:
        if task.completed_at is None:
            task.completed_at = now
    else:
        task.completed_at = None


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tasks = TaskRepository(session)
        self._states = StateService(session)
        self._teams = TeamService(session)
        self._projects = ProjectService(session)
        self._labels = LabelService(session)
        self._activities = ActivityService(session)
        self._notifications = NotificationService(session)

    # --- Чтение -----------------------------------------------------------------

    async def get(self, ctx: AccessContext, *, include_deleted: bool = False) -> Task:
        task = await self._tasks.get_in_workspace(ctx.object_id, ctx.workspace_id)
        if task is None or (task.deleted_at is not None and not include_deleted):
            raise _not_found()
        return task

    async def list_tasks(
        self,
        ctx: AccessContext,
        filters: TaskFilters,
        *,
        limit: int,
        cursor: str | None,
        expand: frozenset[str],
    ) -> TaskPage:
        after = None
        if cursor is not None:
            sort_order, task_id = decode_cursor(cursor, 2)
            try:
                after = (sort_order, UUID(task_id))
            except ValueError as error:
                raise ApiError(400, "invalid_cursor", "Курсор повреждён или устарел") from error
        rows = await self._tasks.page(
            ctx.workspace_id,
            task_visibility(ctx.workspace_role, ctx.principal.user_id),
            filters,
            after=after,
            limit=limit,
        )
        items, next_cursor, has_more = paginate(rows, limit, lambda t: (t.sort_order, t.id))
        return TaskPage(
            items=await self.present(ctx, items, expand),
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def run_query(
        self,
        ctx: AccessContext,
        conditions: Sequence[ColumnElement[bool]],
        sort: SortSpec,
        *,
        group_by: ViewGroupBy | None,
        group: str | None,
        cursor: str | None,
        limit: int,
        expand: frozenset[str],
    ) -> list[TaskGroup]:
        """Выполнение view: условия фильтров плюс видимость читателя.

        Без `group` — первые страницы всех групп; с `group` — страница одной группы
        (колонки доски листаются независимо). Курсор имеет смысл только внутри группы.
        """
        if group is not None and group_by is None:
            raise ApiError(400, "invalid_group", "View не группирует задачи", {"group": group})
        if cursor is not None and group_by is not None and group is None:
            raise ApiError(400, "invalid_cursor", "Курсор листает одну группу — укажите group")
        scoped = [task_visibility(ctx.workspace_role, ctx.principal.user_id), *conditions]
        only = (parse_group_key(group_by, group),) if group_by and group is not None else None
        after = sort.decode(cursor) if cursor is not None else None

        rows = await self._tasks.view_page(
            ctx.workspace_id,
            scoped,
            sort,
            group_by=group_by,
            only_group=only,
            after=after,
            limit=limit,
        )
        if group_by is None:
            counts: list[tuple[Any, int]] = [
                (None, await self._tasks.view_count(ctx.workspace_id, scoped))
            ]
        else:
            counts = await self._tasks.view_group_counts(ctx.workspace_id, scoped, group_by)
            if only is not None:
                # Пустая колонка доски — группа с нулём, а не пропажа группы.
                counts = [(key, count) for key, count in counts if key == only[0]] or [(only[0], 0)]

        grouped: dict[Any, list[Task]] = {key: [] for key, _ in counts}
        for task, key in rows:
            grouped.setdefault(key, []).append(task)
        order = await self._group_order(ctx, group_by, [key for key, _ in counts])

        result = []
        for key, count in sorted(counts, key=lambda item: order(item[0])):
            tasks = grouped.get(key, [])
            page, has_more = tasks[:limit], len(tasks) > limit
            result.append(
                TaskGroup(
                    key=format_group_key(key),
                    count=count,
                    items=await self.present(ctx, page, expand),
                    next_cursor=sort.encode(page[-1]) if has_more else None,
                    has_more=has_more,
                )
            )
        return result

    async def _group_order(
        self, ctx: AccessContext, group_by: ViewGroupBy | None, keys: Sequence[Any]
    ) -> Any:
        """Функция-ключ порядка групп. Группа без значения — всегда последняя."""
        present = [key for key in keys if key is not None]
        rank: dict[Any, tuple[Any, ...]] = {}
        if group_by == ViewGroupBy.PRIORITY:
            rank = {key: (key or NO_PRIORITY_RANK,) for key in present}
        elif group_by == ViewGroupBy.DUE_DATE:
            rank = {key: (key,) for key in present}
        elif group_by == ViewGroupBy.STATE:
            types = list(StateType)
            rank = {
                state.id: (types.index(StateType(state.type)), state.position, state.name)
                for state in await self._states.get_many(present)
            }
        elif group_by == ViewGroupBy.ASSIGNEE:
            rank = {
                user.id: (user.full_name.lower(), str(user.id))
                for user in await UserService(self._session).get_many(present)
            }
        elif group_by == ViewGroupBy.PROJECT:
            rank = {
                project.id: (project.name.lower(), str(project.id))
                for project in await self._projects.get_many(present, ctx.workspace_id)
            }
        elif group_by == ViewGroupBy.LABEL:
            rank = {
                label.id: (label.name.lower(), str(label.id))
                for label in await self._labels.get_many(present, ctx.workspace_id)
            }

        def order(key: Any) -> tuple[int, tuple[Any, ...]]:
            if key is None:
                return (2, ())
            return (0, rank[key]) if key in rank else (1, (str(key),))

        return order

    async def subtasks(self, ctx: AccessContext, expand: frozenset[str]) -> list[TaskRead]:
        task = await self.get(ctx)
        children = await self._tasks.children(
            task.id, ctx.workspace_id, task_visibility(ctx.workspace_role, ctx.principal.user_id)
        )
        return await self.present(ctx, children, expand)

    async def present(
        self, ctx: AccessContext, tasks: Sequence[Task], expand: Collection[str] = ()
    ) -> list[TaskRead]:
        """Задачи → ответы: ключ, `label_ids` и запрошенные развёрнутые поля."""
        if not tasks:
            return []
        workspace_id = ctx.workspace_id
        keys = await self._team_keys({task.team_id for task in tasks}, workspace_id)
        labels = await self._labels.labels_by_task([task.id for task in tasks])

        users: dict[UUID, UserBrief] = {}
        if {"assignee", "creator"} & set(expand):
            ids = {t.assignee_id for t in tasks if t.assignee_id} | {t.creator_id for t in tasks}
            users = {
                user.id: UserBrief.model_validate(user)
                for user in await UserService(self._session).get_many(ids)
            }
        states: dict[UUID, StateBrief] = {}
        if "state" in expand:
            states = {
                state.id: StateBrief.model_validate(state)
                for state in await self._states.get_many(list({t.state_id for t in tasks}))
            }
        projects: dict[UUID, ProjectBrief] = {}
        if "project" in expand:
            project_ids = list({t.project_id for t in tasks if t.project_id})
            projects = {
                project.id: ProjectBrief.model_validate(project)
                for project in await self._projects.get_many(project_ids, workspace_id)
            }
        parents: dict[UUID, TaskBrief] = {}
        if "parent" in expand:
            parents = await self._briefs(ctx, {t.parent_id for t in tasks if t.parent_id})

        result = []
        for task in tasks:
            fields: dict[str, Any] = {
                "id": task.id,
                "key": f"{keys[task.team_id]}-{task.number}",
                "workspace_id": task.workspace_id,
                "team_id": task.team_id,
                "project_id": task.project_id,
                "number": task.number,
                "title": task.title,
                "description": task.description,
                "state_id": task.state_id,
                "assignee_id": task.assignee_id,
                "creator_id": task.creator_id,
                "priority": task.priority,
                "due_date": task.due_date,
                "parent_id": task.parent_id,
                "label_ids": [label.id for label in labels.get(task.id, [])],
                "sort_order": task.sort_order,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "deleted_at": task.deleted_at,
            }
            if "assignee" in expand:
                fields["assignee"] = users.get(task.assignee_id) if task.assignee_id else None
            if "creator" in expand:
                fields["creator"] = users.get(task.creator_id)
            if "state" in expand:
                fields["state"] = states.get(task.state_id)
            if "labels" in expand:
                fields["labels"] = [
                    LabelBrief.model_validate(label) for label in labels.get(task.id, [])
                ]
            if "project" in expand:
                fields["project"] = projects.get(task.project_id) if task.project_id else None
            if "parent" in expand:
                fields["parent"] = parents.get(task.parent_id) if task.parent_id else None
            if "relations" in expand:
                fields["relations"] = await self.relations(ctx, task)
            result.append(TaskRead(**fields))
        return result

    async def key_of(self, task: Task) -> str:
        keys = await self._team_keys({task.team_id}, task.workspace_id)
        return f"{keys[task.team_id]}-{task.number}"

    # --- Создание и изменение ---------------------------------------------------

    async def create(self, ctx: AccessContext, data: TaskCreate) -> Task:
        """Без commit: коммитит `IdempotencyService` вместе с сохранённым ответом."""
        team_id = ctx.team
        if data.team_id is not None and data.team_id != team_id:
            raise ApiError(
                400,
                "project_team_mismatch",
                "Проект принадлежит другой команде",
                {"team_id": str(data.team_id), "project_id": str(data.project_id)},
            )
        state = await self._state_in_team(team_id, data.state_id)
        parent_id = await self._parent(ctx, data.parent_id, task=None)
        await self._check_assignee(ctx.workspace_id, team_id, ctx.project_id, data.assignee_id)

        # Номер — первым: UPDATE строки команды держит её блокировку до конца
        # транзакции, и концы списков ниже читаются уже без гонки.
        number = await self._teams.next_task_number(team_id)
        last = await self._tasks.edge_sort_order(team_id, last=True)
        now = datetime.now(UTC)
        task = Task(
            workspace_id=ctx.workspace_id,
            team_id=team_id,
            project_id=ctx.project_id,
            number=number,
            title=data.title,
            description=data.description,
            assignee_id=data.assignee_id,
            creator_id=ctx.principal.user_id,
            priority=data.priority,
            due_date=data.due_date,
            parent_id=parent_id,
            sort_order=key_between(last, None),
            created_at=now,
            updated_at=now,
        )
        _apply_state(task, state, now)
        await self._tasks.add(task)
        if data.label_ids:
            await self._labels.replace_for_task(
                workspace_id=ctx.workspace_id,
                team_id=team_id,
                task_id=task.id,
                label_ids=data.label_ids,
            )
        await self._record(ctx, task, ActivityType.TASK_CREATED)
        if task.assignee_id is not None:
            await self._notify_assigned(ctx, task)
        return task

    async def update(self, ctx: AccessContext, data: TaskUpdate) -> Task:
        task = await self.get(ctx)
        changes = data.model_dump(exclude_unset=True)
        now = datetime.now(UTC)
        events: list[tuple[ActivityType, dict[str, Any]]] = []

        if "project_id" in changes and changes["project_id"] != task.project_id:
            await self._check_location(ctx, task.team_id, changes["project_id"])
            events.append(
                (
                    ActivityType.PROJECT_CHANGED,
                    {"from": _id(task.project_id), "to": _id(changes["project_id"])},
                )
            )
            task.project_id = changes["project_id"]

        if "parent_id" in changes:
            parent_id = await self._parent(ctx, changes["parent_id"], task=task)
            if parent_id != task.parent_id:
                events.append(
                    (
                        ActivityType.PARENT_CHANGED,
                        {"from": _id(task.parent_id), "to": _id(parent_id)},
                    )
                )
                task.parent_id = parent_id

        if "state_id" in changes and changes["state_id"] != task.state_id:
            events.append(await self._change_state(task, changes["state_id"], now))

        assigned = False
        if "assignee_id" in changes and changes["assignee_id"] != task.assignee_id:
            await self._check_assignee(
                ctx.workspace_id, task.team_id, task.project_id, changes["assignee_id"]
            )
            events.append(
                (
                    ActivityType.ASSIGNEE_CHANGED,
                    {"from": _id(task.assignee_id), "to": _id(changes["assignee_id"])},
                )
            )
            task.assignee_id = changes["assignee_id"]
            assigned = task.assignee_id is not None

        if "title" in changes and changes["title"] != task.title:
            events.append(
                (ActivityType.TITLE_CHANGED, {"from": task.title, "to": changes["title"]})
            )
            task.title = changes["title"]
        if "description" in changes and changes["description"] != task.description:
            # Текст описания в историю не пишется: бывает большим, а лента append-only.
            events.append((ActivityType.DESCRIPTION_CHANGED, {}))
            task.description = changes["description"]
        if "priority" in changes and changes["priority"] != task.priority:
            events.append(
                (ActivityType.PRIORITY_CHANGED, {"from": task.priority, "to": changes["priority"]})
            )
            task.priority = changes["priority"]
        if "due_date" in changes and changes["due_date"] != task.due_date:
            events.append(
                (
                    ActivityType.DUE_DATE_CHANGED,
                    {"from": _day(task.due_date), "to": _day(changes["due_date"])},
                )
            )
            task.due_date = changes["due_date"]

        if events:
            task.updated_at = now
            await self._session.flush()
            for kind, payload in events:
                await self._record(ctx, task, kind, payload)
            if assigned:
                await self._notify_assigned(ctx, task)
            await self._session.commit()
        return task

    async def move(self, ctx: AccessContext, data: TaskMove) -> Task:
        task = await self.get(ctx)
        # Перестановки одной команды — по очереди: соседи читаются без гонки.
        await self._teams.lock(task.team_id)
        now = datetime.now(UTC)
        events: list[tuple[ActivityType, dict[str, Any]]] = []

        if data.state_id is not None and data.state_id != task.state_id:
            events.append(await self._change_state(task, data.state_id, now))

        if data.after_id or data.before_id or data.position:
            old_key = task.sort_order
            new_key = await self._place(ctx, task, data)
            if new_key != old_key:
                task.sort_order = new_key
                events.append((ActivityType.TASK_MOVED, {"from": old_key, "to": new_key}))

        if events:
            task.updated_at = now
            await self._session.flush()
            for kind, payload in events:
                await self._record(ctx, task, kind, payload)
            await self._session.commit()
        return task

    async def delete(self, ctx: AccessContext) -> None:
        task = await self.get(ctx)
        task.deleted_at = datetime.now(UTC)
        task.updated_at = task.deleted_at
        await self._record(ctx, task, ActivityType.TASK_DELETED)
        await self._session.commit()

    async def restore(self, ctx: AccessContext) -> Task:
        task = await self.get(ctx, include_deleted=True)
        if task.deleted_at is not None:
            task.deleted_at = None
            task.updated_at = datetime.now(UTC)
            await self._record(ctx, task, ActivityType.TASK_RESTORED)
            await self._session.commit()
        return task

    async def set_labels(self, ctx: AccessContext, label_ids: Collection[UUID]) -> Task:
        task = await self.get(ctx)
        added, removed = await self._labels.replace_for_task(
            workspace_id=task.workspace_id,
            team_id=task.team_id,
            task_id=task.id,
            label_ids=label_ids,
        )
        for label in added:
            await self._record(
                ctx, task, ActivityType.LABEL_ADDED, {"label_id": str(label.id), "name": label.name}
            )
        for label in removed:
            await self._record(
                ctx,
                task,
                ActivityType.LABEL_REMOVED,
                {"label_id": str(label.id), "name": label.name},
            )
        if added or removed:
            task.updated_at = datetime.now(UTC)
            await self._session.commit()
        return task

    # --- Связи ------------------------------------------------------------------

    async def add_relation(self, ctx: AccessContext, data: RelationCreate) -> RelationRead:
        task = await self.get(ctx)
        target = await self._visible_ref(ctx, data.target_id, error="target_not_found")
        if target.id == task.id:
            raise ApiError(400, "relation_self", "Задача не может быть связана сама с собой")

        kind, task_is_source = _STORED[data.type]
        source, dest = (task, target) if task_is_source else (target, task)
        symmetric = kind == RelationType.RELATES_TO
        if await self._tasks.relation_exists(source.id, dest.id, kind, symmetric=symmetric):
            raise ApiError(409, "relation_exists", "Такая связь уже есть")
        # Новая связь source → dest замыкает цикл, если dest уже блокирует source.
        if kind == RelationType.BLOCKS and await self._tasks.blocks_reachable(dest.id, source.id):
            raise ApiError(
                400,
                "relation_cycle",
                "Связь создаёт цикл блокировок",
                {"source": await self.key_of(source), "target": await self.key_of(dest)},
            )

        relation = await self._tasks.add_relation(
            TaskRelation(
                workspace_id=ctx.workspace_id,
                source_task_id=source.id,
                target_task_id=dest.id,
                type=kind,
                created_by=ctx.principal.user_id,
            )
        )
        await self._record_relation(ctx, ActivityType.RELATION_ADDED, relation, task, target)
        await self._session.commit()
        return RelationRead(id=relation.id, type=data.type, task=await self._brief(target))

    async def remove_relation(self, ctx: AccessContext, relation_id: UUID) -> None:
        task = await self.get(ctx)
        relation = await self._tasks.get_relation(relation_id, ctx.workspace_id)
        if relation is None or task.id not in (relation.source_task_id, relation.target_task_id):
            raise ApiError(404, "relation_not_found", "Связь не найдена")
        other_id = (
            relation.target_task_id
            if relation.source_task_id == task.id
            else relation.source_task_id
        )
        other = await self._tasks.get_in_workspace(other_id, ctx.workspace_id)
        await self._tasks.delete_relation(relation)
        if other is not None:
            await self._record_relation(ctx, ActivityType.RELATION_REMOVED, relation, task, other)
        await self._session.commit()

    async def relations(self, ctx: AccessContext, task: Task) -> list[RelationRead]:
        """Связи со стороны задачи; связанные задачи, невидимые читателю, не показываются."""
        relations = await self._tasks.relations_of(task.id)
        others = {
            r.target_task_id if r.source_task_id == task.id else r.source_task_id for r in relations
        }
        briefs = await self._briefs(ctx, others)
        result = []
        for relation in relations:
            outgoing = relation.source_task_id == task.id
            other = relation.target_task_id if outgoing else relation.source_task_id
            if other not in briefs:
                continue
            kind = RelationType(relation.type)
            view = _FORWARD[kind] if outgoing else _INVERSE[kind]
            result.append(RelationRead(id=relation.id, type=view, task=briefs[other]))
        return result

    # --- Для других модулей -----------------------------------------------------

    async def find_live(self, task_id: UUID, workspace_id: UUID) -> Task | None:
        """Неудалённая задача по id — без проверки прав, их проверил вызывающий."""
        task = await self._tasks.get_in_workspace(task_id, workspace_id)
        return task if task is not None and task.deleted_at is None else None

    async def record(
        self,
        ctx: AccessContext,
        task: Task,
        kind: ActivityType,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Событие в истории задачи от другого модуля. Без commit."""
        await self._record(ctx, task, kind, payload)

    async def count_in_state(self, state_id: UUID) -> int:
        return await self._tasks.count_in_state(state_id)

    async def reassign_state(
        self, ctx: AccessContext, source: WorkflowState, target: WorkflowState
    ) -> None:
        """Перенос задач удаляемого статуса — с историей у каждой. Без commit."""
        now = datetime.now(UTC)
        for task in await self._tasks.in_state(source.id):
            _apply_state(task, target, now)
            task.updated_at = now
            await self._record(
                replace(ctx, object_id=task.id),
                task,
                ActivityType.STATE_CHANGED,
                {"from": _state_payload(source), "to": _state_payload(target)},
            )

    # --- Внутреннее -------------------------------------------------------------

    async def _record(
        self,
        ctx: AccessContext,
        task: Task,
        kind: ActivityType,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self._activities.record(
            workspace_id=task.workspace_id,
            task_id=task.id,
            actor=ctx.principal,
            kind=kind,
            payload=payload,
        )

    async def _record_relation(
        self,
        ctx: AccessContext,
        kind: ActivityType,
        relation: TaskRelation,
        task: Task,
        other: Task,
    ) -> None:
        """Связь пишется в историю обеих задач — с типом, прочитанным с каждой стороны."""
        stored = RelationType(relation.type)
        task_view = _FORWARD[stored] if relation.source_task_id == task.id else _INVERSE[stored]
        other_view = _FORWARD[stored] if relation.source_task_id == other.id else _INVERSE[stored]
        for subject, view, counterpart in ((task, task_view, other), (other, other_view, task)):
            await self._record(
                ctx,
                subject,
                kind,
                {
                    "relation_id": str(relation.id),
                    "type": view,
                    "task_id": str(counterpart.id),
                    "task_key": await self.key_of(counterpart),
                },
            )

    async def _notify_assigned(self, ctx: AccessContext, task: Task) -> None:
        assert task.assignee_id is not None
        await self._notifications.notify(
            workspace_id=task.workspace_id,
            user_id=task.assignee_id,
            kind=NotificationType.ASSIGNED,
            actor_id=ctx.principal.user_id,
            task_id=task.id,
        )

    async def _change_state(
        self, task: Task, state_id: UUID, now: datetime
    ) -> tuple[ActivityType, dict[str, Any]]:
        new = await self._state_in_team(task.team_id, state_id)
        old = await self._states.get_in_team(task.state_id, task.team_id)
        assert old is not None, "статус задачи принадлежит её команде"
        _apply_state(task, new, now)
        return ActivityType.STATE_CHANGED, {"from": _state_payload(old), "to": _state_payload(new)}

    async def _state_in_team(self, team_id: UUID, state_id: UUID | None) -> WorkflowState:
        if state_id is None:
            return await self._states.default_for_team(team_id)
        state = await self._states.get_in_team(state_id, team_id)
        if state is None:
            raise ApiError(
                400,
                "invalid_state",
                "Статус не принадлежит команде задачи",
                {"state_id": str(state_id)},
            )
        return state

    async def _check_assignee(
        self, workspace_id: UUID, team_id: UUID, project_id: UUID | None, assignee_id: UUID | None
    ) -> None:
        """Исполнитель обязан видеть задачу — иначе назначение раскрыло бы её чужому."""
        if assignee_id is None:
            return
        on: AccessTarget = "project" if project_id else "team"
        row = await load_access(self._session, assignee_id, on, project_id or team_id)
        role = compute_effective_role(row) if row is not None else None
        if row is None or row.workspace_id != workspace_id or role is None:
            raise ApiError(
                400,
                "assignee_no_access",
                "У исполнителя нет доступа к задаче",
                {"assignee_id": str(assignee_id)},
            )

    async def _check_location(
        self, ctx: AccessContext, team_id: UUID, project_id: UUID | None
    ) -> None:
        """Переносить задачу можно только туда, где актор вправе её создать."""
        if project_id is None:
            await resolve_access(
                self._session,
                ctx.principal,
                on="team",
                object_id=team_id,
                permission=Permission.TASK_CREATE,
            )
            return
        # Сначала права: невидимый проект отвечает 404, не выдавая своей команды.
        target = await resolve_access(
            self._session,
            ctx.principal,
            on="project",
            object_id=project_id,
            permission=Permission.TASK_CREATE,
        )
        if target.team_id != team_id:
            raise ApiError(
                400,
                "project_team_mismatch",
                "Проект принадлежит другой команде",
                {"project_id": str(project_id)},
            )

    async def _visible_ref(self, ctx: AccessContext, ref: str, *, error: str) -> Task:
        """Ссылка из тела запроса → видимая актору неудалённая задача того же workspace."""
        task_id = await task_ref_to_id(
            self._session, ctx.principal.user_id, ref, workspace_id=ctx.workspace_id
        )
        task = await self._tasks.get_in_workspace(task_id, ctx.workspace_id) if task_id else None
        if task is not None and task.deleted_at is None:
            row = await load_access(self._session, ctx.principal.user_id, "task", task.id)
            role = compute_effective_role(row) if row is not None else None
            if role is not None and role >= EffectiveRole.VIEWER:
                return task
        raise ApiError(400, error, f"Задача {ref} не найдена", {"task": ref})

    async def _parent(
        self, ctx: AccessContext, ref: str | None, *, task: Task | None
    ) -> UUID | None:
        if ref is None:
            return None
        parent = await self._visible_ref(ctx, ref, error="parent_not_found")
        height = 1
        if task is not None:
            descendants, height = await self._tasks.subtree(task.id)
            if parent.id == task.id or parent.id in descendants:
                raise ApiError(400, "parent_cycle", "Подзадача не может стать родителем предка")
        if await self._tasks.depth(parent.id) + height > MAX_DEPTH:
            raise ApiError(
                400,
                "parent_depth_exceeded",
                f"Подзадачи вкладываются не глубже {MAX_DEPTH} уровней",
                {"max_depth": MAX_DEPTH},
            )
        return parent.id

    async def _place(self, ctx: AccessContext, task: Task, data: TaskMove) -> str:
        """Новый ключ задачи по якорю. Совпавшие ключи соседей или слишком длинный
        результат — перегенерация ключей всей команды и повторный расчёт."""
        anchor: Task | None = None
        ref = data.after_id or data.before_id
        if ref is not None:
            anchor = await self._visible_ref(ctx, ref, error="invalid_move_anchor")
            if anchor.team_id != task.team_id or anchor.id == task.id:
                raise ApiError(
                    400,
                    "invalid_move_anchor",
                    "Якорь перестановки — другая задача той же команды",
                    {"task": ref},
                )

        for attempt in range(2):
            low, high = await self._bounds(task, anchor, data)
            if low is None or high is None or low < high:
                key = key_between(low, high)
                if len(key) <= MAX_SORT_KEY:
                    return key
            if attempt == 0:
                await self._rebalance(task.team_id)
        raise AssertionError("после перегенерации ключ обязан найтись")

    async def _bounds(
        self, task: Task, anchor: Task | None, data: TaskMove
    ) -> tuple[str | None, str | None]:
        team_id = task.team_id
        if data.position == "top":
            return None, await self._tasks.edge_sort_order(team_id, last=False, exclude=task.id)
        if data.position == "bottom":
            return await self._tasks.edge_sort_order(team_id, last=True, exclude=task.id), None
        assert anchor is not None
        if data.after_id is not None:
            after = await self._tasks.neighbour_sort_order(
                team_id, anchor, after=True, exclude=task.id
            )
            return anchor.sort_order, after
        before = await self._tasks.neighbour_sort_order(
            team_id, anchor, after=False, exclude=task.id
        )
        return before, anchor.sort_order

    async def _rebalance(self, team_id: UUID) -> None:
        tasks = await self._tasks.team_order(team_id)
        for task, key in zip(tasks, keys_between(None, None, len(tasks)), strict=True):
            task.sort_order = key
        await self._session.flush()

    async def _team_keys(self, team_ids: Collection[UUID], workspace_id: UUID) -> dict[UUID, str]:
        teams = await self._teams.get_many(list(team_ids), workspace_id)
        return {team.id: team.key for team in teams}

    async def _brief(self, task: Task) -> TaskBrief:
        return TaskBrief(id=task.id, key=await self.key_of(task), title=task.title)

    async def _briefs(
        self, ctx: AccessContext, task_ids: Collection[UUID]
    ) -> dict[UUID, TaskBrief]:
        """Краткие карточки задач, видимых читателю; невидимые и удалённые отбрасываются."""
        visible = await self._tasks.visible_ids(
            task_ids, ctx.workspace_id, task_visibility(ctx.workspace_role, ctx.principal.user_id)
        )
        tasks = await self._tasks.get_many(visible, ctx.workspace_id)
        keys = await self._team_keys({task.team_id for task in tasks}, ctx.workspace_id)
        return {
            task.id: TaskBrief(
                id=task.id, key=f"{keys[task.team_id]}-{task.number}", title=task.title
            )
            for task in tasks
        }

    # --- Для админ-панели: только числа -------------------------------------------

    async def counts_by_workspace(self, ids: Collection[UUID]) -> dict[UUID, int]:
        return await self._tasks.live_counts_by_workspace(ids)

    async def count(self) -> int:
        return await self._tasks.live_count()
