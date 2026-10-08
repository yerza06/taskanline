"""MCP-сервер TasKanLine: инструменты, ресурсы и промпты поверх SDK.

Сервер — тонкая обёртка: каждый вызов открывает клиент SDK с токеном пользователя и
`Resolver` для имён, своих HTTP-вызовов и запросов в базу нет. Права целиком задаёт токен:
сервер получает от API те же 403 и 404, что получил бы сам пользователь.

Описание инструмента — это промпт: оно говорит модели не только что делает инструмент,
но и когда его выбирать. Качество работы модели зависит от них сильнее, чем от схем.
"""

import functools
import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from taskanline_mcp import __version__
from taskanline_mcp.config import Settings
from taskanline_mcp.errors import ToolInputError, message_for
from taskanline_mcp.present import (
    DETAIL_EXPAND,
    PRIORITY_NAMES,
    PRIORITY_VALUES,
    TAIL_LIMIT,
    TASK_EXPAND,
    task_brief,
    task_card,
)
from taskanline_sdk import TasKanLineClient, TasKanLineError
from taskanline_sdk.models import Comment, Task
from taskanline_sdk.resolve import Resolver

INSTRUCTIONS = """TasKanLine — трекер задач. Задачи принадлежат командам (ключ вроде ENG) и \
называются ключами вида ENG-142 — используй ключи, а не UUID, и в ответах человеку тоже.
Начни с list_teams: он вернёт команды вместе с их статусами — не угадывай названия статусов.
Для «что в работе / мои задачи / баги» — search_tasks; если человек настроил сохранённый срез, \
быстрее list_views и run_view. Удалять задачи и менять роли через этот сервер нельзя."""

StateType = Literal["backlog", "unstarted", "started", "completed", "canceled"]
Priority = Literal["urgent", "high", "medium", "low", "none"]
ProjectStatus = Literal["planned", "in_progress", "paused", "completed", "canceled"]
RelationType = Literal["blocks", "blocked_by", "relates_to", "duplicates"]
Include = Literal["comments", "activity", "subtasks", "relations"]
Clearable = Literal["description", "assignee", "due_date", "project", "parent"]

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
IDEMPOTENT_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
# Сколько комментариев перебираем, чтобы показать последние 20: дальше задача — уже не
# предмет для диалога, а в карточке есть счётчик.
COMMENT_SCAN_LIMIT = 500


def _result(data: dict[str, Any]) -> CallToolResult:
    text = json.dumps(data, ensure_ascii=False, default=str)
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=data)


def _error(text: str) -> CallToolResult:
    return CallToolResult(is_error=True, content=[TextContent(type="text", text=text)])


def _guarded[**P](
    fn: Callable[P, Awaitable[dict[str, Any]]],
) -> Callable[P, Awaitable[CallToolResult]]:
    """Ответ инструмента — JSON; ошибка SDK — текст с подсказкой и `isError`, не трассировка."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> CallToolResult:
        try:
            return _result(await fn(*args, **kwargs))
        except (TasKanLineError, ToolInputError) as error:
            return _error(message_for(error))

    # Схему MCPServer строит по сигнатуре: параметры — исходные, ответ — готовый результат.
    wrapper.__signature__ = inspect.signature(fn).replace(  # type: ignore[attr-defined]
        return_annotation=CallToolResult
    )
    return wrapper


def _due(value: str) -> str:
    """`today+7d`, `@today+7d`, `today` или ISO-дата → значение грамматики views."""
    raw = value.strip()
    if raw.startswith("today"):
        raw = "@" + raw
    return raw


def _bearer(ctx: Context) -> str | None:
    headers = ctx.headers or {}
    raw = headers.get("authorization") or headers.get("Authorization")
    if raw and raw.lower().startswith("bearer "):
        return raw[7:].strip() or None
    return None


class TaskanlineServer:
    """Собирает `MCPServer` по настройкам. `transport` — шов для тестов: подменяет сеть."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: Callable[[], httpx.AsyncBaseTransport | None] = lambda: None,
        client_options: dict[str, Any] | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._client_options = client_options or {}
        self.mcp = MCPServer(
            "taskanline", title="TasKanLine", instructions=INSTRUCTIONS, version=__version__
        )
        self._register_read_tools()
        if not settings.read_only:
            self._register_write_tools()
        self._register_resources()
        self._register_prompts()

    # --- Сессия вызова ----------------------------------------------------------------

    @asynccontextmanager
    async def session(self, ctx: Context | None) -> AsyncIterator[Resolver]:
        if self.settings.token_from_header:
            token = _bearer(ctx) if ctx is not None else None
            if token is None:
                raise ToolInputError(
                    "Нужен заголовок Authorization: Bearer <токен TasKanLine>. "
                    "Токен выпускается в веб-интерфейсе: Профиль → Токены."
                )
        else:
            token = self.settings.token
        async with TasKanLineClient(
            self.settings.api_url,
            token,
            transport=self._transport(),
            **self._client_options,
        ) as client:
            yield Resolver(client, workspace=self.settings.workspace, restrict=True)

    def _limit(self, requested: int | None, default: int = 25) -> int:
        return max(1, min(requested or default, self.settings.max_items))

    def _brief(self, task: Task) -> dict[str, Any]:
        return task_brief(task, self.settings.web_url)

    def _card(self, task: Task) -> dict[str, Any]:
        return task_card(task, self.settings.web_url)

    def _tool(
        self, fn: Callable[..., Awaitable[dict[str, Any]]], annotations: ToolAnnotations
    ) -> None:
        self.mcp.add_tool(
            _guarded(fn),
            name=fn.__name__,
            description=inspect.cleandoc(fn.__doc__ or ""),
            annotations=annotations,
        )

    # --- Чтение -----------------------------------------------------------------------

    def _register_read_tools(self) -> None:
        server = self

        async def list_workspaces(ctx: Context) -> dict[str, Any]:
            """Рабочие пространства, доступные пользователю, с его ролью в каждом.

            Обычно нужен один раз в начале диалога — и только если пространств несколько:
            при единственном остальные инструменты выбирают его сами.
            """
            async with server.session(ctx) as r:
                roles = {m.workspace_id: m.role for m in (await r.me()).memberships.workspaces}
                return {
                    "workspaces": [
                        {"id": str(s.id), "slug": s.slug, "name": s.name, "role": roles.get(s.id)}
                        for s in await r.workspaces()
                    ]
                }

        async def list_teams(
            ctx: Context,
            workspace: Annotated[
                str | None,
                Field(description="Slug или id; при единственном доступном можно опустить"),
            ] = None,
        ) -> dict[str, Any]:
            """Команды рабочего пространства: ключи (ENG) и рабочие статусы каждой.

            Вызывай до создания задач и смены статусов: статусы у команд свои, и только
            отсюда видно, как они называются. Не угадывай названия.
            """
            async with server.session(ctx) as r:
                space = await r.workspace(workspace)
                teams = await r.client.teams.all(space.id)
                return {
                    "workspace": space.slug,
                    "teams": [
                        {
                            "key": team.key,
                            "name": team.name,
                            "states": [
                                {"name": s.name, "type": s.type}
                                for s in sorted(await r.states(team.id), key=lambda s: s.position)
                            ],
                        }
                        for team in teams
                    ],
                }

        async def list_projects(
            ctx: Context,
            team: Annotated[str | None, Field(description="Ключ команды, например ENG")] = None,
            status: Annotated[ProjectStatus | None, Field(description="Статус проекта")] = None,
        ) -> dict[str, Any]:
            """Проекты команды (или всех команд). Нужен, чтобы узнать имя проекта для
            search_tasks и create_task или посмотреть сроки проектов."""
            async with server.session(ctx) as r:
                teams = [await r.team(team)] if team else await r.teams()
                found = []
                for item in teams:
                    for project in await r.client.projects.all(item.id):
                        if status is None or project.status == status:
                            found.append(
                                {
                                    "id": str(project.id),
                                    "name": project.name,
                                    "team": item.key,
                                    "status": project.status,
                                    "target_date": project.target_date,
                                }
                            )
                return {"projects": found[: server.settings.max_items]}

        async def search_tasks(
            ctx: Context,
            query: Annotated[str | None, Field(description="Подстрока в заголовке")] = None,
            team: Annotated[str | None, Field(description="Ключ команды, например ENG")] = None,
            project: Annotated[str | None, Field(description="Имя или id проекта")] = None,
            assignee: Annotated[
                str | None, Field(description="Email исполнителя или me — текущий пользователь")
            ] = None,
            state_type: Annotated[
                list[StateType] | None,
                Field(description="Типы статусов; «в работе» — started, «не начато» — unstarted"),
            ] = None,
            label: Annotated[
                list[str] | None, Field(description="Названия меток — любая из них")
            ] = None,
            priority: Annotated[Priority | None, Field(description="Приоритет")] = None,
            due_before: Annotated[
                str | None, Field(description="Срок раньше даты: YYYY-MM-DD или today+7d")
            ] = None,
            limit: Annotated[
                int | None, Field(ge=1, le=50, description="1–50, по умолчанию 25")
            ] = None,
            cursor: Annotated[
                str | None, Field(description="next_cursor предыдущего ответа")
            ] = None,
        ) -> dict[str, Any]:
            """Основной инструмент чтения: найти задачи по команде, исполнителю, статусу,
            меткам, приоритету и сроку. Все условия соединяются через И.

            Без единого фильтра ищет только открытые задачи (unstarted и started): «покажи
            все задачи» почти никогда не настоящее намерение. Описание в ответе обрезано до
            200 символов — полный текст и комментарии даёт get_task. Если человек ссылается
            на сохранённый срез («мои баги», «спринт»), сначала проверь list_views.
            """
            async with server.session(ctx) as r:
                filters: dict[str, Any] = {}
                scope = await r.team(team) if team else None
                if scope is not None:
                    filters["team_id"] = {"op": "in", "value": [str(scope.id)]}
                if query:
                    filters["title"] = {"op": "contains", "value": query}
                if project:
                    filters["project_id"] = {
                        "op": "in",
                        "value": [str((await r.project(project)).id)],
                    }
                if assignee:
                    who = "@me" if assignee.lower() == "me" else str(await r.user_id(assignee))
                    filters["assignee_id"] = {"op": "in", "value": [who]}
                if label:
                    ids = await r.label_ids(label, scope.id if scope else None)
                    filters["label_id"] = {"op": "in", "value": [str(i) for i in ids]}
                if priority:
                    filters["priority"] = {"op": "in", "value": [PRIORITY_VALUES[priority]]}
                if due_before:
                    filters["due_date"] = {"op": "lt", "value": _due(due_before)}
                if state_type:
                    filters["state_type"] = {"op": "in", "value": list(state_type)}
                if not filters or set(filters) == {"team_id"}:
                    filters["state_type"] = {"op": "in", "value": ["unstarted", "started"]}
                space = await r.workspace()
                result = await r.client.tasks.query(
                    space.id,
                    filters=filters,
                    cursor=cursor,
                    limit=server._limit(limit),
                    expand=TASK_EXPAND,
                )
                (group,) = result.groups
                return {
                    "tasks": [server._brief(task) for task in group.items],
                    "total": group.count,
                    "has_more": group.has_more,
                    "next_cursor": group.next_cursor,
                }

        async def get_task(
            ctx: Context,
            key: Annotated[str, Field(description="Ключ задачи, например ENG-142, или UUID")],
            include: Annotated[
                list[Include] | None,
                Field(description="Что добавить; по умолчанию comments и subtasks"),
            ] = None,
        ) -> dict[str, Any]:
            """Полная карточка задачи: описание целиком, родитель, связи и по запросу
            последние 20 комментариев, последние 20 событий истории, подзадачи.

            Вызывай перед тем, как работать с задачей или пересказывать её человеку:
            search_tasks показывает только обрезанное описание.
            """
            parts = set(include or ("comments", "subtasks"))
            async with server.session(ctx) as r:
                task = await r.task(key, expand=DETAIL_EXPAND)
                card = server._card(task)
                if "relations" not in parts:
                    card.pop("relations")
                if "subtasks" in parts:
                    subtasks = await r.client.tasks.subtasks(task.id, expand=TASK_EXPAND)
                    card["subtasks"] = [server._brief(item) for item in subtasks][:TAIL_LIMIT]
                if "comments" in parts:
                    card.update(await server._comments(r, task))
                if "activity" in parts:
                    page = await r.client.tasks.activities(task.id, limit=TAIL_LIMIT)
                    card["activity"] = [
                        {
                            "type": item.type,
                            "via_token": item.actor_token_id is not None,
                            "payload": item.payload,
                            "at": item.created_at.isoformat(),
                        }
                        for item in page.items
                    ]
                return card

        async def list_views(ctx: Context) -> dict[str, Any]:
            """Сохранённые срезы задач, которые настроил человек: имя, описание и фильтры
            словами. Если просьба похожа на один из них — run_view точнее и дешевле, чем
            собирать те же условия в search_tasks."""
            async with server.session(ctx) as r:
                views = await r.client.views.all((await r.workspace()).id)
                return {
                    "views": [
                        {
                            "id": str(view.id),
                            "name": view.name,
                            "description": view.description,
                            "scope": view.scope,
                            "group_by": view.group_by,
                            "filters": await describe_filters(r, view.filters),
                        }
                        for view in views
                    ]
                }

        async def run_view(
            ctx: Context,
            view: Annotated[str, Field(description="Имя или id из list_views")],
            limit: Annotated[
                int | None, Field(ge=1, le=50, description="Задач на группу, 1–50")
            ] = None,
        ) -> dict[str, Any]:
            """Выполнить сохранённый срез: задачи по его фильтрам, сортировке и группам.
            Результат свой у каждого человека — `@me` в фильтрах значит «текущий пользователь»."""
            async with server.session(ctx) as r:
                found = await r.view(view)
                result = await r.client.views.run(
                    found.id, limit=server._limit(limit), expand=TASK_EXPAND
                )
                labels = await group_names(r, found.group_by)
                return {
                    "view": found.name,
                    "group_by": found.group_by,
                    "groups": [
                        {
                            "key": group.key,
                            "name": labels.get(group.key or "", group.key),
                            "count": group.count,
                            "tasks": [server._brief(task) for task in group.items],
                            "has_more": group.has_more,
                        }
                        for group in result.groups
                    ],
                }

        for fn in (
            list_workspaces,
            list_teams,
            list_projects,
            search_tasks,
            get_task,
            list_views,
            run_view,
        ):
            self._tool(fn, READ)

    async def _comments(self, r: Resolver, task: Task) -> dict[str, Any]:
        """Последние 20 комментариев и сколько их всего."""
        items: list[Comment] = []
        cursor: str | None = None
        while len(items) < COMMENT_SCAN_LIMIT:
            page = await r.client.tasks.comments(task.id, limit=100, cursor=cursor)
            items.extend(page.items)
            if not page.has_more:
                break
            cursor = page.next_cursor
        authors = {m.user_id: m.email for m in await r.members()}
        return {
            "comments_total": len(items),
            "comments": [
                {
                    "author": authors.get(item.author_id),
                    "via_token": item.author_token_id is not None,
                    "body": item.body,
                    "at": item.created_at.isoformat(),
                }
                for item in items[-TAIL_LIMIT:]
            ],
        }

    # --- Запись -----------------------------------------------------------------------

    def _register_write_tools(self) -> None:
        server = self

        async def create_task(
            ctx: Context,
            title: Annotated[str, Field(min_length=1, max_length=500, description="Заголовок")],
            team: Annotated[
                str | None,
                Field(
                    description="Ключ команды; можно опустить, если команда одна или задан project"
                ),
            ] = None,
            description: Annotated[str | None, Field(description="Описание, Markdown")] = None,
            project: Annotated[str | None, Field(description="Имя или id проекта")] = None,
            state: Annotated[
                str | None,
                Field(description="Название статуса из list_teams; по умолчанию — статус команды"),
            ] = None,
            assignee: Annotated[str | None, Field(description="Email или me")] = None,
            priority: Annotated[Priority | None, Field(description="Приоритет")] = None,
            due_date: Annotated[str | None, Field(description="Срок, YYYY-MM-DD")] = None,
            labels: Annotated[
                list[str] | None,
                Field(description="Существующие метки; несуществующая — ошибка, а не создание"),
            ] = None,
            parent: Annotated[
                str | None, Field(description="Ключ родительской задачи — для подзадачи")
            ] = None,
        ) -> dict[str, Any]:
            """Создать задачу. Возвращает её ключ и url — сошлись на них в ответе человеку.

            Создавай, только когда человек об этом попросил или подтвердил список; перед
            этим проверь названия статусов и меток через list_teams, а не угадывай их.
            """
            async with server.session(ctx) as r:
                found_project = await r.project(project) if project else None
                if found_project is not None:
                    team_id = found_project.team_id
                else:
                    team_id = (await r.require_team(team)).id
                fields: dict[str, Any] = {}
                if description is not None:
                    fields["description"] = description
                if state:
                    fields["state_id"] = (await r.state(team_id, state)).id
                if assignee:
                    fields["assignee_id"] = await r.user_id(assignee)
                if priority:
                    fields["priority"] = PRIORITY_VALUES[priority]
                if due_date:
                    fields["due_date"] = due_date
                if labels:
                    fields["label_ids"] = await r.label_ids(labels, team_id)
                if parent:
                    fields["parent_id"] = parent
                task = await r.client.tasks.create(
                    title=title,
                    team_id=None if found_project else team_id,
                    project_id=found_project.id if found_project else None,
                    expand=TASK_EXPAND,
                    **fields,
                )
                return {"created": server._brief(task)}

        async def update_task(
            ctx: Context,
            key: Annotated[str, Field(description="Ключ задачи, например ENG-142")],
            title: Annotated[str | None, Field(min_length=1, max_length=500)] = None,
            description: Annotated[str | None, Field(description="Новое описание целиком")] = None,
            state: Annotated[str | None, Field(description="Название статуса команды")] = None,
            assignee: Annotated[str | None, Field(description="Email или me")] = None,
            priority: Annotated[Priority | None, Field(description="Приоритет")] = None,
            due_date: Annotated[str | None, Field(description="Срок, YYYY-MM-DD")] = None,
            project: Annotated[str | None, Field(description="Имя или id проекта")] = None,
            parent: Annotated[str | None, Field(description="Ключ родительской задачи")] = None,
            clear: Annotated[
                list[Clearable] | None,
                Field(description='Поля, которые нужно очистить, например ["due_date"]'),
            ] = None,
        ) -> dict[str, Any]:
            """Изменить задачу. Меняются только переданные поля; непереданные остаются как
            были. Чтобы очистить поле, перечисли его в clear — пустое значение не очищает.

            Для смены исполнителя или статуса понятнее assign_task и update_task_state.
            """
            async with server.session(ctx) as r:
                task = await r.task(key)
                cleared = set(clear or ())
                given = {
                    "description": description,
                    "assignee": assignee,
                    "due_date": due_date,
                    "project": project,
                    "parent": parent,
                }
                both = sorted(name for name in cleared if given.get(name) is not None)
                if both:
                    raise ToolInputError(
                        f"Поле {', '.join(both)} одновременно передано и указано в clear — "
                        "выберите одно."
                    )
                changes: dict[str, Any] = {
                    {"assignee": "assignee_id", "project": "project_id", "parent": "parent_id"}.get(
                        name, name
                    ): None
                    for name in cleared
                }
                if title is not None:
                    changes["title"] = title
                if description is not None:
                    changes["description"] = description
                if state:
                    changes["state_id"] = (await r.state(task.team_id, state)).id
                if assignee:
                    changes["assignee_id"] = await r.user_id(assignee)
                if priority:
                    changes["priority"] = PRIORITY_VALUES[priority]
                if due_date:
                    changes["due_date"] = due_date
                if project:
                    changes["project_id"] = (await r.project(project)).id
                if parent:
                    changes["parent_id"] = parent
                if not changes:
                    raise ToolInputError("Нечего менять: передайте хотя бы одно поле или clear.")
                updated = await r.client.tasks.update(task.id, expand=TASK_EXPAND, **changes)
                return {"updated": server._brief(updated)}

        async def assign_task(
            ctx: Context,
            key: Annotated[str, Field(description="Ключ задачи, например ENG-142")],
            assignee: Annotated[
                str | None, Field(description="Email, me или null — снять исполнителя")
            ],
        ) -> dict[str, Any]:
            """Назначить исполнителя задачи или снять его (null). Исполнителем может быть
            только участник рабочего пространства."""
            async with server.session(ctx) as r:
                task = await r.task(key)
                who = await r.user_id(assignee) if assignee else None
                updated = await r.client.tasks.update(task.id, assignee_id=who, expand=TASK_EXPAND)
                return {"updated": server._brief(updated)}

        async def update_task_state(
            ctx: Context,
            key: Annotated[str, Field(description="Ключ задачи, например ENG-142")],
            state: Annotated[
                str, Field(description="Название статуса команды, например In Progress")
            ],
        ) -> dict[str, Any]:
            """Перевести задачу в другой статус: взять в работу, закрыть, отменить.
            Названия статусов — из list_teams; при неизвестном ошибка перечислит допустимые."""
            async with server.session(ctx) as r:
                task = await r.task(key)
                target = await r.state(task.team_id, state)
                updated = await r.client.tasks.update(
                    task.id, state_id=target.id, expand=TASK_EXPAND
                )
                return {"updated": server._brief(updated)}

        async def comment_task(
            ctx: Context,
            key: Annotated[str, Field(description="Ключ задачи, например ENG-142")],
            body: Annotated[
                str,
                Field(min_length=1, max_length=20000, description="Markdown; @email — упоминание"),
            ],
        ) -> dict[str, Any]:
            """Оставить комментарий к задаче: отчёт о сделанном, вопрос, решение. Упомянутый
            через @email участник получит уведомление."""
            async with server.session(ctx) as r:
                task = await r.task(key)
                comment = await r.client.tasks.comment(task.id, body)
                return {"commented": task.key, "comment_id": str(comment.id)}

        async def link_tasks(
            ctx: Context,
            source: Annotated[str, Field(description="Ключ задачи, от которой идёт связь")],
            target: Annotated[str, Field(description="Ключ второй задачи")],
            type: Annotated[  # noqa: A002 — имя параметра — часть контракта инструмента
                RelationType,
                Field(description="source blocks target, source blocked_by target, …"),
            ],
        ) -> dict[str, Any]:
            """Связать две задачи: блокирует, заблокирована, связана, дублирует."""
            async with server.session(ctx) as r:
                task = await r.task(source)
                relation = await r.client.tasks.add_relation(task.id, kind=type, target=target)
                return {"linked": {"source": task.key, "type": type, "target": relation.task.key}}

        self._tool(create_task, WRITE)
        for fn in (update_task, assign_task, update_task_state):
            self._tool(fn, IDEMPOTENT_WRITE)
        self._tool(comment_task, WRITE)
        self._tool(link_tasks, IDEMPOTENT_WRITE)

    # --- Ресурсы ----------------------------------------------------------------------

    def _register_resources(self) -> None:
        server = self

        async def read(ctx: Context, build: Callable[[Resolver], Awaitable[str]]) -> str:
            try:
                async with server.session(ctx) as r:
                    return await build(r)
            except (TasKanLineError, ToolInputError) as error:
                raise ResourceError(message_for(error)) from error

        @self.mcp.resource(
            "taskanline://workspace/{slug}",
            mime_type="text/markdown",
            description="Обзор пространства: команды, открытые задачи по командам",
        )
        async def workspace_resource(slug: str, ctx: Context) -> str:
            async def build(r: Resolver) -> str:
                space = await r.workspace(slug)
                lines = [f"# {space.name} ({space.slug})", ""]
                for team in await r.client.teams.all(space.id):
                    result = await r.client.tasks.query(
                        space.id,
                        filters={
                            "team_id": {"op": "in", "value": [str(team.id)]},
                            "state_type": {"op": "in", "value": ["unstarted", "started"]},
                        },
                        limit=1,
                    )
                    lines.append(
                        f"- **{team.key}** — {team.name}: открытых задач {result.groups[0].count}"
                    )
                return "\n".join(lines)

            return await read(ctx, build)

        @self.mcp.resource(
            "taskanline://team/{key}",
            mime_type="text/markdown",
            description="Команда: статусы, проекты, метки, участники",
        )
        async def team_resource(key: str, ctx: Context) -> str:
            async def build(r: Resolver) -> str:
                team = await r.team(key)
                states = sorted(await r.states(team.id), key=lambda s: s.position)
                projects = await r.client.projects.all(team.id)
                labels = [
                    label.name for label in await r.labels() if label.team_id in (None, team.id)
                ]
                members = await r.client.teams.members(team.id)
                return "\n".join(
                    [
                        f"# {team.key} — {team.name}",
                        "",
                        "## Статусы",
                        *[f"- {s.name} ({s.type})" for s in states],
                        "",
                        "## Проекты",
                        *([f"- {p.name} — {p.status}" for p in projects] or ["- нет"]),
                        "",
                        "## Метки",
                        ", ".join(sorted(labels)) or "нет",
                        "",
                        "## Участники",
                        *[f"- {m.email} ({m.role})" for m in members],
                    ]
                )

            return await read(ctx, build)

        @self.mcp.resource(
            "taskanline://project/{project_id}",
            mime_type="text/markdown",
            description="Проект: описание, сроки, задачи по типам статусов",
        )
        async def project_resource(project_id: str, ctx: Context) -> str:
            async def build(r: Resolver) -> str:
                project = await r.project(project_id)
                result = await r.client.tasks.query(
                    project.workspace_id,
                    filters={"project_id": {"op": "in", "value": [str(project.id)]}},
                    limit=server.settings.max_items,
                    expand=("state",),
                )
                counts: dict[str, int] = {}
                for task in result.groups[0].items:
                    kind = task.state.type if task.state else "unknown"
                    counts[kind] = counts.get(kind, 0) + 1
                return "\n".join(
                    [
                        f"# {project.name}",
                        "",
                        f"Статус: {project.status}. Начало: {project.start_date or '—'}. "
                        f"Цель: {project.target_date or '—'}.",
                        "",
                        project.description or "Описания нет.",
                        "",
                        f"## Задачи ({result.groups[0].count})",
                        *[f"- {kind}: {count}" for kind, count in sorted(counts.items())],
                    ]
                )

            return await read(ctx, build)

        @self.mcp.resource(
            "taskanline://task/{key}",
            mime_type="text/markdown",
            description="Задача в Markdown: поля, описание, последние комментарии",
        )
        async def task_resource(key: str, ctx: Context) -> str:
            async def build(r: Resolver) -> str:
                task = await r.task(key, expand=DETAIL_EXPAND)
                card = server._card(task)
                comments = (await server._comments(r, task))["comments"]
                lines = [
                    f"# {task.key}: {task.title}",
                    "",
                    f"- Статус: {card['state']} ({card['state_type']})",
                    f"- Исполнитель: {card['assignee'] or '—'}",
                    f"- Приоритет: {card['priority']}",
                    f"- Срок: {card['due_date'] or '—'}",
                    f"- Метки: {', '.join(card['labels']) or '—'}",
                    f"- Проект: {card['project'] or '—'}",
                    f"- Ссылка: {card['url']}",
                    "",
                    task.description or "Описания нет.",
                ]
                if comments:
                    lines += ["", "## Комментарии"]
                    lines += [
                        f"**{c['author'] or '?'}** ({c['at']}):\n{c['body']}" for c in comments
                    ]
                return "\n".join(lines)

            return await read(ctx, build)

    # --- Промпты ----------------------------------------------------------------------

    def _register_prompts(self) -> None:
        writable = not self.settings.read_only

        @self.mcp.prompt(description="Разобрать задачу и предложить подзадачи")
        def breakdown_task(key: str, max_subtasks: str = "5") -> str:
            create = (
                f"После явного подтверждения пользователя создай подзадачи через create_task "
                f"с parent={key}."
                if writable
                else "Сервер в режиме только для чтения — создавать подзадачи не нужно."
            )
            return (
                f"Прочитай задачу {key} через get_task (с comments и subtasks). Предложи не "
                f"больше {max_subtasks} подзадач: короткий заголовок и одно предложение о том, "
                f"что считается сделанным. Не дублируй уже существующие подзадачи. {create}"
            )

        @self.mcp.prompt(description="Сводка по проекту")
        def project_status(project: str) -> str:
            return (
                f"Подготовь сводку по проекту «{project}». Найди его задачи через search_tasks "
                f"(project={project}; отдельно state_type=[completed], [started], [unstarted]). "
                "Раздели на: сделано, в работе, заблокировано (get_task, relations), "
                "просрочено (срок раньше сегодняшнего и задача не закрыта). Для каждой задачи — "
                "ключ и одна строка. В конце — главный риск проекта."
            )

        @self.mcp.prompt(description="За что взяться дальше")
        def whats_next(team: str, assignee: str = "me") -> str:
            return (
                f"Помоги выбрать следующую задачу в команде {team} для {assignee}. Возьми "
                f"search_tasks(team={team}, assignee={assignee}, state_type=[unstarted, started]) "
                "и при необходимости без assignee. Учитывай приоритет, срок и блокировки "
                "(get_task, relations: blocked_by). Предложи одну задачу и две запасные, каждую — "
                "ключ и почему именно она."
            )

        @self.mcp.prompt(description="Сводка изменений для стендапа")
        def standup(team: str, since: str = "yesterday") -> str:
            return (
                f"Подготовь стендап команды {team} с {since}. Найди задачи команды через "
                f"search_tasks(team={team}, state_type=[started, completed]) и для изменившихся "
                "посмотри историю через get_task(include=[activity]). Сгруппируй по людям: "
                "что сделано, что в работе, что мешает. Ключи задач — обязательно."
            )


async def describe_filters(r: Resolver, filters: dict[str, Any]) -> str:
    """Фильтры view словами: «исполнитель: я; тип статуса не: completed» — с именами."""
    if not filters:
        return "без фильтров"
    names: dict[str, str] = {}
    teams = await r.teams()
    names.update({str(team.id): team.key for team in teams})
    for team in teams:
        names.update({str(s.id): f"{s.name} ({team.key})" for s in await r.states(team.id)})
    names.update({str(label.id): label.name for label in await r.labels()})
    names.update({str(m.user_id): m.email for m in await r.members()})
    names.update({str(p.id): p.name for p in await r.projects()})
    names["@me"] = "я"
    titles = {
        "team_id": "команда",
        "project_id": "проект",
        "state_id": "статус",
        "state_type": "тип статуса",
        "assignee_id": "исполнитель",
        "creator_id": "автор",
        "label_id": "метка",
        "parent_id": "родитель",
        "priority": "приоритет",
        "due_date": "срок",
        "created_at": "создана",
        "updated_at": "изменена",
        "completed_at": "закрыта",
        "title": "заголовок",
        "has_parent": "подзадача",
        "is_blocked": "заблокирована",
    }
    ops = {
        "in": "",
        "nin": " не",
        "eq": "",
        "lt": " <",
        "lte": " ≤",
        "gt": " >",
        "gte": " ≥",
        "is_null": " пусто",
        "not_null": " задано",
        "contains": " содержит",
    }
    parts = []
    for field, spec in filters.items():
        op = str(spec.get("op"))
        value = spec.get("value")
        if field == "priority":
            value = (
                [PRIORITY_NAMES.get(v, v) for v in value]
                if isinstance(value, list)
                else PRIORITY_NAMES.get(value, value)
            )
        if isinstance(value, list):
            shown = ", ".join(names.get(str(item), str(item)) for item in value)
        elif value is None:
            shown = ""
        else:
            shown = str(value)
        label = titles.get(field, field) + ops.get(op, f" {op}")
        parts.append(f"{label}: {shown}" if shown else label)
    return "; ".join(parts)


async def group_names(r: Resolver, group_by: str | None) -> dict[str, str]:
    """Имя ключа группы: id статуса → «In Progress», 1 → urgent."""
    match group_by:
        case "priority":
            return {str(key): name for key, name in PRIORITY_NAMES.items()}
        case "state":
            return {
                str(state.id): state.name
                for team in await r.teams()
                for state in await r.states(team.id)
            }
        case "assignee":
            return {str(member.user_id): member.email for member in await r.members()}
        case "project":
            return {str(project.id): project.name for project in await r.projects()}
        case "label":
            return {str(label.id): label.name for label in await r.labels()}
    return {}


def build(settings: Settings, **options: Any) -> MCPServer:
    return TaskanlineServer(settings, **options).mcp


__all__ = ["TaskanlineServer", "build", "describe_filters", "group_names"]
