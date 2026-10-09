"""`tkl task`: центральная группа команд.

Ключ задачи принимается и как `ENG-142`, и как UUID, регистр не важен. Изменяющие
команды выводят задачу после изменения — агенту не нужен второй вызов, чтобы
убедиться, что всё применилось.
"""

from typing import Annotated, Any

import typer

from taskanline_cli.commands import Team, Workspace, is_empty, parse_sort, text_source
from taskanline_cli.context import Session, run
from taskanline_cli.errors import not_found, usage
from taskanline_cli.filters import PRIORITIES, parse, priority_value
from taskanline_cli.output import Item, Listing
from taskanline_cli.present import DETAIL_EXPAND, TASK_EXPAND, compact_task, dump, task_item
from taskanline_cli.present import task_listing as listing_of
from taskanline_sdk.models import Task

app = typer.Typer(help="Задачи", no_args_is_help=True)

Key = Annotated[str, typer.Argument(metavar="KEY", help="Ключ задачи (ENG-142) или UUID")]
PRIORITY_HELP = ", ".join(PRIORITIES)


async def _show(session: Session, task: Task) -> Item:
    fresh = await session.client.tasks.get(task.id, expand=DETAIL_EXPAND)
    return task_item(fresh, session.settings.web_url)


@app.command("list")
def list_(
    filter_: Annotated[
        str | None,
        typer.Option("--filter", "-f", help='Например "assignee:me state-type:started"'),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 50,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    sort: Annotated[str, typer.Option("--sort", help="Поле[:desc] или -поле")] = "manual",
    team: Team = None,
    all_teams: Annotated[
        bool, typer.Option("--all-teams", help="Не ограничивать командой профиля")
    ] = False,
    workspace: Workspace = None,
) -> None:
    """Список задач по фильтру."""
    terms = parse(filter_ or "")
    sort_by, direction = parse_sort(sort)

    async def action(session: Session) -> Listing:
        space = await session.workspace(workspace)
        in_filter = any(term.field == "team" for term in terms)
        scope = None if in_filter else await session.default_team(team, all_teams=all_teams)
        filters = await session.compile(terms, scope)
        result = await session.client.tasks.query(
            space.id,
            filters=filters,
            sort_by=sort_by,
            sort_direction=direction,
            cursor=cursor,
            limit=limit,
            expand=TASK_EXPAND,
        )
        (group,) = result.groups
        return listing_of(
            group.items,
            session.settings.web_url,
            next_cursor=group.next_cursor,
            has_more=group.has_more,
            total_hint=group.count,
        )

    run(action)


@app.command()
def show(
    key: Key,
    comments: Annotated[bool, typer.Option("--comments", help="С комментариями")] = False,
    activity: Annotated[bool, typer.Option("--activity", help="С историей изменений")] = False,
    subtasks: Annotated[bool, typer.Option("--subtasks", help="С подзадачами")] = False,
) -> None:
    """Задача целиком."""

    async def action(session: Session) -> Item:
        task = await session.task(key, expand=DETAIL_EXPAND)
        extra: dict[str, Any] = {}
        if subtasks:
            found = await session.client.tasks.subtasks(task.id, expand=TASK_EXPAND)
            extra["subtasks"] = [compact_task(item, session.settings.web_url) for item in found]
        if comments:
            page = await session.client.tasks.comments(task.id, limit=100)
            extra["comments"] = [
                {
                    "id": str(item.id),
                    "author_id": str(item.author_id),
                    "via_token": item.author_token_id is not None,
                    "body": item.body,
                    "created_at": item.created_at.isoformat(),
                }
                for item in page.items
            ]
        if activity:
            page_a = await session.client.tasks.activities(task.id, limit=100)
            extra["activity"] = [dump(item) for item in page_a.items]
        return task_item(task, session.settings.web_url, **extra)

    run(action)


async def _fields(
    session: Session,
    *,
    team_id: Any,
    title: str | None,
    description: str | None,
    state: str | None,
    assignee: str | None,
    priority: str | None,
    due: str | None,
    parent: str | None,
) -> dict[str, Any]:
    """Опции create/update → поля API. `none` очищает необязательное поле."""
    fields: dict[str, Any] = {}
    if title is not None:
        fields["title"] = title
    if description is not None:
        fields["description"] = None if is_empty(description) else text_source(description)
    if state is not None:
        fields["state_id"] = (await session.state(team_id, state)).id
    if assignee is not None:
        fields["assignee_id"] = None if is_empty(assignee) else await session.user_id(assignee)
    if priority is not None:
        if priority not in PRIORITIES and priority not in {"0", "1", "2", "3", "4"}:
            raise usage("invalid_priority", f"Приоритет «{priority}»", f"Можно: {PRIORITY_HELP}")
        fields["priority"] = priority_value(priority)
    if due is not None:
        fields["due_date"] = None if is_empty(due) else due
    if parent is not None:
        fields["parent_id"] = None if is_empty(parent) else parent
    return fields


Title = Annotated[str | None, typer.Option("--title")]
Description = Annotated[
    str | None, typer.Option("--description", "-d", help="Текст, @файл или - для stdin")
]
State = Annotated[str | None, typer.Option("--state", help="Имя статуса команды")]
Assignee = Annotated[str | None, typer.Option("--assignee", help="Email, me или none")]
Priority = Annotated[str | None, typer.Option("--priority", help=PRIORITY_HELP)]
Due = Annotated[str | None, typer.Option("--due", help="YYYY-MM-DD или none")]
Labels = Annotated[list[str] | None, typer.Option("--label", help="Повторяемая")]
Parent = Annotated[str | None, typer.Option("--parent", help="Ключ родительской задачи")]
Project = Annotated[str | None, typer.Option("--project", help="id или имя проекта")]


@app.command()
def create(
    title: Annotated[str, typer.Option("--title")],
    team: Team = None,
    project: Project = None,
    description: Description = None,
    state: State = None,
    assignee: Assignee = None,
    priority: Priority = None,
    due: Due = None,
    label: Labels = None,
    parent: Parent = None,
    workspace: Workspace = None,
) -> None:
    """Создать задачу."""

    async def action(session: Session) -> Item:
        await session.workspace(workspace)
        found_project = await session.project(project) if project else None
        if found_project is not None:
            team_id = found_project.team_id
        else:
            team_id = (await session.require_team(team)).id
        fields = await _fields(
            session,
            team_id=team_id,
            title=None,
            description=description,
            state=state,
            assignee=assignee,
            priority=priority,
            due=due,
            parent=parent,
        )
        if label:
            fields["label_ids"] = await session.label_ids(label, team_id)
        task = await session.client.tasks.create(
            title=title,
            team_id=None if found_project else team_id,
            project_id=found_project.id if found_project else None,
            **fields,
        )
        return await _show(session, task)

    run(action)


@app.command()
def update(
    key: Key,
    title: Title = None,
    project: Annotated[str | None, typer.Option("--project", help="id, имя или none")] = None,
    description: Description = None,
    state: State = None,
    assignee: Assignee = None,
    priority: Priority = None,
    due: Due = None,
    label: Labels = None,
    parent: Annotated[str | None, typer.Option("--parent", help="Ключ или none")] = None,
) -> None:
    """Изменить задачу: меняются только переданные поля."""

    async def action(session: Session) -> Item:
        task = await session.task(key)
        fields = await _fields(
            session,
            team_id=task.team_id,
            title=title,
            description=description,
            state=state,
            assignee=assignee,
            priority=priority,
            due=due,
            parent=parent,
        )
        if project is not None:
            fields["project_id"] = (
                None if is_empty(project) else (await session.project(project)).id
            )
        if label is not None:
            await session.client.tasks.set_labels(
                task.id, await session.label_ids(label, task.team_id)
            )
        if fields:
            task = await session.client.tasks.update(task.id, **fields)
        elif label is None:
            raise usage("nothing_to_update", "Нечего менять", "Передайте хотя бы одну опцию")
        return await _show(session, task)

    run(action)


@app.command()
def assign(
    key: Key, who: Annotated[str, typer.Argument(metavar="EMAIL_OR_ME", help="Email, me, none")]
) -> None:
    """Назначить исполнителя."""

    async def action(session: Session) -> Item:
        task = await session.task(key)
        user = None if is_empty(who) else await session.user_id(who)
        return await _show(session, await session.client.tasks.update(task.id, assignee_id=user))

    run(action)


@app.command("state")
def set_state(key: Key, name: Annotated[str, typer.Argument(metavar="STATE_NAME")]) -> None:
    """Сменить статус по имени: tkl task state ENG-142 "In Progress"."""

    async def action(session: Session) -> Item:
        task = await session.task(key)
        state = await session.state(task.team_id, name)
        return await _show(session, await session.client.tasks.update(task.id, state_id=state.id))

    run(action)


@app.command()
def close(
    key: Key,
    canceled: Annotated[bool, typer.Option("--canceled", help="Отменить, а не завершить")] = False,
) -> None:
    """Перевести в первый статус типа completed (или canceled)."""
    kind = "canceled" if canceled else "completed"

    async def action(session: Session) -> Item:
        task = await session.task(key)
        states = sorted(await session.states(task.team_id), key=lambda state: state.position)
        target = next((state for state in states if state.type == kind), None)
        if target is None:
            raise not_found("state_not_found", f"У команды нет статуса типа {kind}")
        return await _show(session, await session.client.tasks.update(task.id, state_id=target.id))

    run(action)


@app.command()
def move(
    key: Key,
    after: Annotated[str | None, typer.Option("--after", help="Сразу после задачи")] = None,
    before: Annotated[str | None, typer.Option("--before", help="Сразу перед задачей")] = None,
    top: Annotated[bool, typer.Option("--top", help="В начало")] = False,
    bottom: Annotated[bool, typer.Option("--bottom", help="В конец")] = False,
) -> None:
    """Переставить задачу в ручном порядке команды."""
    chosen = [after is not None, before is not None, top, bottom]
    if sum(chosen) != 1:
        raise usage("invalid_move", "Укажите ровно одно: --after, --before, --top или --bottom")
    position = "top" if top else "bottom" if bottom else None

    async def action(session: Session) -> Item:
        task = await session.client.tasks.move(key, after=after, before=before, position=position)
        return await _show(session, task)

    run(action)


@app.command()
def label(
    key: Key,
    add: Annotated[list[str] | None, typer.Option("--add", help="Повторяемая")] = None,
    remove: Annotated[list[str] | None, typer.Option("--remove", help="Повторяемая")] = None,
) -> None:
    """Добавить и снять метки."""
    if not add and not remove:
        raise usage("nothing_to_update", "Нечего менять", "Передайте --add или --remove")

    async def action(session: Session) -> Item:
        task = await session.task(key)
        current = list(task.label_ids)
        for label_id in await session.label_ids(add or [], task.team_id):
            if label_id not in current:
                current.append(label_id)
        dropped = set(await session.label_ids(remove or [], task.team_id))
        updated = await session.client.tasks.set_labels(
            task.id, [label_id for label_id in current if label_id not in dropped]
        )
        return await _show(session, updated)

    run(action)


@app.command()
def link(
    key: Key,
    blocks: Annotated[str | None, typer.Option("--blocks", help="Эта задача блокирует")] = None,
    blocked_by: Annotated[
        str | None, typer.Option("--blocked-by", help="Эту задачу блокирует")
    ] = None,
    relates_to: Annotated[str | None, typer.Option("--relates-to")] = None,
    duplicates: Annotated[str | None, typer.Option("--duplicates", help="Дублирует")] = None,
) -> None:
    """Связать с другой задачей."""
    given = {
        kind: target
        for kind, target in {
            "blocks": blocks,
            "blocked_by": blocked_by,
            "relates_to": relates_to,
            "duplicates": duplicates,
        }.items()
        if target is not None
    }
    if len(given) != 1:
        raise usage("invalid_link", "Укажите ровно одну связь: --blocks, --blocked-by, …")
    ((kind, target),) = given.items()

    async def action(session: Session) -> Item:
        task = await session.task(key)
        await session.client.tasks.add_relation(task.id, kind=kind, target=target)
        return await _show(session, task)

    run(action)


@app.command()
def unlink(
    key: Key,
    other: Annotated[str, typer.Argument(metavar="OTHER")],
    kind: Annotated[
        str | None,
        typer.Option("--type", help="blocks, blocked_by, relates_to, duplicates, duplicated_by"),
    ] = None,
) -> None:
    """Удалить связь с другой задачей."""

    async def action(session: Session) -> Item:
        task = await session.task(key, expand=("relations",))
        matches = [
            relation
            for relation in task.relations or []
            if other.upper() in (relation.task.key, str(relation.task.id).upper())
            and (kind is None or relation.type == kind.replace("-", "_"))
        ]
        if not matches:
            raise not_found("relation_not_found", f"Связи {task.key} с {other.upper()} нет")
        for relation in matches:
            await session.client.tasks.remove_relation(task.id, relation.id)
        return await _show(session, task)

    run(action)


@app.command()
def comment(
    key: Key,
    source: Annotated[str | None, typer.Argument(metavar="[-]", help="- — текст из stdin")] = None,
    message: Annotated[str | None, typer.Option("--message", "-m", help="Текст")] = None,
    file: Annotated[str | None, typer.Option("--file", help="Файл с текстом")] = None,
) -> None:
    """Оставить комментарий: -m "текст", --file PATH или - (stdin)."""
    sources = [value for value in (message, file, source) if value is not None]
    if len(sources) != 1 or (source is not None and source != "-"):
        raise usage("invalid_comment", "Укажите ровно одно: -m ТЕКСТ, --file ПУТЬ или -")
    body = message if message is not None else text_source("-" if source else f"@{file}")
    if not body.strip():
        raise usage("empty_comment", "Пустой комментарий")

    async def action(session: Session) -> Item:
        created = await session.client.tasks.comment(key, body)
        return Item(dump(created))

    run(action)


@app.command()
def delete(key: Key) -> None:
    """Мягкое удаление; вернуть — tkl task restore."""

    async def action(session: Session) -> Item:
        task = await session.task(key)
        await session.client.tasks.delete(task.id)
        return Item({"key": task.key, "deleted": True}, ident="key")

    run(action)


@app.command()
def restore(key: Key) -> None:
    """Восстановить удалённую задачу."""

    async def action(session: Session) -> Item:
        return await _show(session, await session.client.tasks.restore(key))

    run(action)
