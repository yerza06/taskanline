"""`tkl view`: сохранённые срезы задач.

`tkl view run` — самая полезная команда для агента: сложный фильтр человек настраивает
один раз в вебе, а агент обращается к нему по имени.
"""

from typing import Annotated, Any

import typer

from taskanline_cli.commands import Team, Workspace, parse_sort
from taskanline_cli.context import Session, run
from taskanline_cli.filters import parse
from taskanline_cli.output import Column, Item, Listing, col
from taskanline_cli.present import PRIORITY_NAMES, TASK_COLUMNS, TASK_EXPAND, compact_task, dump
from taskanline_sdk.models import View

app = typer.Typer(help="Сохранённые views", no_args_is_help=True)

Ref = Annotated[str, typer.Argument(metavar="ID_OR_NAME")]
GROUP_BY = "state, assignee, priority, project, label, due_date"
VIEW_COLUMNS = [
    col("NAME", "name"),
    col("SCOPE", "scope"),
    col("GROUP", "group_by"),
    col("LAYOUT", "layout"),
    col("ID", "id"),
]


@app.command("list")
def list_(
    scope: Annotated[str | None, typer.Option("--scope", help="user, team, workspace")] = None,
    workspace: Workspace = None,
) -> None:
    """Views, видимые мне: личные, команд и общие."""

    async def action(session: Session) -> Listing:
        space = await session.workspace(workspace)
        views = await session.client.views.all(space.id)
        found = [view for view in views if scope is None or view.scope == scope]
        return Listing([dump(view) for view in found], VIEW_COLUMNS)

    run(action)


@app.command()
def show(ref: Ref, workspace: Workspace = None) -> None:
    """Определение view: фильтры, группировка, сортировка, layout."""

    async def action(session: Session) -> Item:
        await session.workspace(workspace)
        return Item(dump(await session.view(ref)))

    run(action)


async def _group_names(session: Session, view: View) -> dict[str, str]:
    """Человеческое имя ключа группы: id статуса → «In Progress», 1 → urgent."""
    match view.group_by:
        case "priority":
            return {str(key): name for key, name in PRIORITY_NAMES.items()}
        case "state":
            return {
                str(state.id): state.name
                for team in await session.teams()
                for state in await session.states(team.id)
            }
        case "assignee":
            return {str(member.user_id): member.email for member in await session.members()}
        case "project":
            return {str(project.id): project.name for project in await session.projects()}
        case "label":
            return {str(label.id): label.name for label in await session.labels()}
    return {}


@app.command("run")
def run_(
    ref: Ref,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100, help="Задач на группу")] = 50,
    group: Annotated[
        str | None, typer.Option("--group", help="Ключ одной группы; none — без значения")
    ] = None,
    cursor: Annotated[str | None, typer.Option("--cursor", help="Курсор внутри --group")] = None,
    workspace: Workspace = None,
) -> None:
    """Выполнить view и вернуть задачи."""

    async def action(session: Session) -> Listing:
        await session.workspace(workspace)
        view = await session.view(ref)
        result = await session.client.views.run(
            view.id, group=group, limit=limit, cursor=cursor, expand=TASK_EXPAND
        )
        web = session.settings.web_url
        if result.group_by is None:
            (only,) = result.groups
            return Listing(
                [compact_task(task, web) for task in only.items],
                TASK_COLUMNS,
                ident="key",
                next_cursor=only.next_cursor,
                has_more=only.has_more,
                total_hint=only.count,
                extra={"view": view.name, "group_by": None},
            )
        names = await _group_names(session, view)
        items: list[dict[str, Any]] = []
        groups = []
        for found in result.groups:
            name = names.get(found.key or "", found.key) if found.key is not None else None
            groups.append(
                {
                    "key": found.key,
                    "name": name,
                    "count": found.count,
                    "next_cursor": found.next_cursor,
                    "has_more": found.has_more,
                }
            )
            items.extend({**compact_task(task, web), "group": name} for task in found.items)
        return Listing(
            items,
            [Column("GROUP", lambda row: row.get("group") or "—"), *TASK_COLUMNS],
            ident="key",
            has_more=any(found.has_more for found in result.groups),
            total_hint=sum(found.count for found in result.groups),
            extra={"view": view.name, "group_by": result.group_by, "groups": groups},
        )

    run(action)


@app.command()
def create(
    name: Annotated[str, typer.Option("--name")],
    filter_: Annotated[str, typer.Option("--filter", "-f", help="Мини-DSL, как в task list")] = "",
    scope: Annotated[str, typer.Option("--scope", help="user, team, workspace")] = "user",
    team: Team = None,
    group_by: Annotated[str | None, typer.Option("--group-by", help=GROUP_BY)] = None,
    layout: Annotated[str, typer.Option("--layout", help="list, board")] = "list",
    sort: Annotated[str | None, typer.Option("--sort", help="Поле[:desc] или -поле")] = None,
    workspace: Workspace = None,
) -> None:
    """Создать view из фильтра мини-DSL."""
    terms = parse(filter_)
    sort_by, direction = parse_sort(sort) if sort else ("manual", "asc")

    async def action(session: Session) -> Item:
        space = await session.workspace(workspace)
        owner = await session.require_team(team) if scope == "team" else None
        filters = await session.compile(terms, None)
        created = await session.client.views.create(
            space.id,
            name=name,
            scope=scope,
            team_id=owner.id if owner else None,
            filters=filters,
            group_by=group_by,
            layout=layout,
            sort_by=sort_by,
            sort_direction=direction,
        )
        return Item(dump(created))

    run(action)


@app.command()
def delete(ref: Ref, workspace: Workspace = None) -> None:
    """Удалить view."""

    async def action(session: Session) -> Item:
        await session.workspace(workspace)
        view = await session.view(ref)
        await session.client.views.delete(view.id)
        return Item({"id": str(view.id), "name": view.name, "deleted": True})

    run(action)
