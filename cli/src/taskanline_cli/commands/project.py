"""`tkl project`: проекты команд."""

from typing import Annotated, Any

import typer

from taskanline_cli.commands import Team, Workspace, is_empty
from taskanline_cli.context import Session, run
from taskanline_cli.output import Item, Listing, col
from taskanline_cli.present import dump, listing

app = typer.Typer(help="Проекты", no_args_is_help=True)

Ref = Annotated[str, typer.Argument(metavar="ID", help="id или имя проекта")]
STATUSES = "planned, in_progress, paused, completed, canceled"
COLUMNS = [
    col("NAME", "name"),
    col("STATUS", "status"),
    col("TARGET", "target_date"),
    col("ID", "id"),
]


@app.command("list")
def list_(
    team: Team = None,
    status: Annotated[str | None, typer.Option("--status", help=STATUSES)] = None,
    archived: Annotated[bool, typer.Option("--archived", help="Включая архивные")] = False,
    workspace: Workspace = None,
) -> None:
    """Проекты команды или всех видимых команд."""

    async def action(session: Session) -> Listing:
        await session.workspace(workspace)
        chosen = await session.default_team(team)
        teams = [chosen] if chosen else await session.teams()
        found = []
        for item in teams:
            found.extend(await session.client.projects.all(item.id, include_archived=archived))
        if status:
            found = [project for project in found if project.status == status]
        return listing(found, COLUMNS)

    run(action)


@app.command()
def show(ref: Ref) -> None:
    """Детали проекта."""

    async def action(session: Session) -> Item:
        return Item(dump(await session.project(ref)))

    run(action)


async def _changes(
    session: Session, *, lead: str | None, target_date: str | None, **fields: Any
) -> dict[str, Any]:
    changes = {key: value for key, value in fields.items() if value is not None}
    if lead is not None:
        changes["lead_id"] = None if is_empty(lead) else await session.user_id(lead)
    if target_date is not None:
        changes["target_date"] = None if is_empty(target_date) else target_date
    return changes


@app.command()
def create(
    name: Annotated[str, typer.Option("--name")],
    team: Team = None,
    lead: Annotated[str | None, typer.Option("--lead", help="Email или me")] = None,
    target_date: Annotated[str | None, typer.Option("--target-date", help="YYYY-MM-DD")] = None,
    status: Annotated[str | None, typer.Option("--status", help=STATUSES)] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    workspace: Workspace = None,
) -> None:
    """Создать проект."""

    async def action(session: Session) -> Item:
        await session.workspace(workspace)
        owner = await session.require_team(team)
        fields = await _changes(
            session, lead=lead, target_date=target_date, status=status, description=description
        )
        return Item(dump(await session.client.projects.create(owner.id, name=name, **fields)))

    run(action)


@app.command()
def update(
    ref: Ref,
    name: Annotated[str | None, typer.Option("--name")] = None,
    status: Annotated[str | None, typer.Option("--status", help=STATUSES)] = None,
    lead: Annotated[str | None, typer.Option("--lead", help="Email, me или none")] = None,
    target_date: Annotated[str | None, typer.Option("--target-date", help="Дата или none")] = None,
) -> None:
    """Изменить проект."""

    async def action(session: Session) -> Item:
        project = await session.project(ref)
        changes = await _changes(
            session, lead=lead, target_date=target_date, name=name, status=status
        )
        return Item(dump(await session.client.projects.update(project.id, **changes)))

    run(action)


@app.command()
def archive(ref: Ref) -> None:
    """Архивировать проект."""

    async def action(session: Session) -> Item:
        project = await session.project(ref)
        return Item(dump(await session.client.projects.archive(project.id)))

    run(action)


@app.command()
def invite(
    ref: Ref,
    email: Annotated[str, typer.Option("--email")],
    role: Annotated[str, typer.Option("--role", help="viewer, member, lead")] = "member",
) -> None:
    """Пригласить в проект."""

    async def action(session: Session) -> Item:
        project = await session.project(ref)
        invitation = await session.client.invitations.create(
            email=email, scope_type="project", scope_id=project.id, role=role
        )
        return Item(dump(invitation))

    run(action)
