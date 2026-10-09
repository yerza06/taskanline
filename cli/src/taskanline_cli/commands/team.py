"""`tkl team`: команды, их участники и workflow-статусы."""

from typing import Annotated

import typer

from taskanline_cli.commands import Workspace
from taskanline_cli.commands.workspace import MEMBER_COLUMNS
from taskanline_cli.context import Session, run
from taskanline_cli.output import Item, Listing, col
from taskanline_cli.present import dump, listing

app = typer.Typer(help="Команды, участники и статусы", no_args_is_help=True)

Key = Annotated[str, typer.Argument(metavar="KEY", help="Ключ команды, например ENG")]


@app.command("list")
def list_(workspace: Workspace = None) -> None:
    """Команды workspace."""

    async def action(session: Session) -> Listing:
        space = await session.workspace(workspace)
        teams = await session.client.teams.all(space.id)
        return listing(
            teams,
            [col("KEY", "key"), col("NAME", "name"), col("PRIVATE", "is_private")],
            ident="key",
        )

    run(action)


@app.command()
def show(key: Key) -> None:
    """Детали команды."""

    async def action(session: Session) -> Item:
        return Item(dump(await session.team(key)), ident="key")

    run(action)


@app.command()
def create(
    key: Annotated[str, typer.Option("--key", help="2–5 заглавных латинских букв")],
    name: Annotated[str, typer.Option("--name")],
    description: Annotated[str | None, typer.Option("--description")] = None,
    private: Annotated[bool, typer.Option("--private", help="Видна только участникам")] = False,
    workspace: Workspace = None,
) -> None:
    """Создать команду."""

    async def action(session: Session) -> Item:
        space = await session.workspace(workspace)
        team = await session.client.teams.create(
            space.id, key=key, name=name, description=description, is_private=private
        )
        return Item(dump(team), ident="key")

    run(action)


@app.command()
def members(key: Key) -> None:
    """Участники команды."""

    async def action(session: Session) -> Listing:
        team = await session.team(key)
        return listing(await session.client.teams.members(team.id), MEMBER_COLUMNS, ident="email")

    run(action)


@app.command()
def invite(
    key: Key,
    email: Annotated[str, typer.Option("--email")],
    role: Annotated[str, typer.Option("--role", help="member, lead")] = "member",
) -> None:
    """Пригласить в команду."""

    async def action(session: Session) -> Item:
        team = await session.team(key)
        invitation = await session.client.invitations.create(
            email=email, scope_type="team", scope_id=team.id, role=role
        )
        return Item(dump(invitation))

    run(action)


@app.command()
def states(key: Key) -> None:
    """Workflow-статусы команды — с них стоит начинать работу с незнакомой командой."""

    async def action(session: Session) -> Listing:
        team = await session.team(key)
        found = await session.states(team.id)
        return listing(
            found,
            [col("NAME", "name"), col("TYPE", "type"), col("DEFAULT", "is_default")],
            ident="name",
        )

    run(action)
