"""`tkl ws` / `tkl workspace`: рабочие пространства и их участники."""

from typing import Annotated

import typer

from taskanline_cli.context import Session, run
from taskanline_cli.output import Item, Listing, col
from taskanline_cli.present import dump, listing

app = typer.Typer(help="Рабочие пространства (алиас ws)", no_args_is_help=True)

MEMBER_COLUMNS = [col("EMAIL", "email"), col("NAME", "full_name"), col("ROLE", "role")]


@app.command("list")
def list_() -> None:
    """Доступные рабочие пространства."""

    async def action(session: Session) -> Listing:
        spaces = await session.client.workspaces.all()
        return listing(spaces, [col("SLUG", "slug"), col("NAME", "name"), col("ID", "id")])

    run(action)


@app.command()
def show(ref: Annotated[str, typer.Argument(metavar="SLUG_OR_ID")]) -> None:
    """Детали workspace."""

    async def action(session: Session) -> Item:
        return Item(dump(await session.workspace(ref)))

    run(action)


@app.command()
def create(
    name: Annotated[str, typer.Option("--name")],
    slug: Annotated[str, typer.Option("--slug")],
) -> None:
    """Создать workspace."""

    async def action(session: Session) -> Item:
        return Item(dump(await session.client.workspaces.create(name=name, slug=slug)))

    run(action)


@app.command()
def members(ref: Annotated[str | None, typer.Argument(metavar="[WS]")] = None) -> None:
    """Участники с ролями."""

    async def action(session: Session) -> Listing:
        space = await session.workspace(ref)
        found = await session.client.workspaces.members(space.id)
        return listing(found, MEMBER_COLUMNS, ident="email")

    run(action)


@app.command()
def invite(
    ref: Annotated[str | None, typer.Argument(metavar="[WS]")] = None,
    email: Annotated[str, typer.Option("--email")] = "",
    role: Annotated[str, typer.Option("--role", help="guest, member, admin")] = "member",
) -> None:
    """Пригласить в workspace."""

    async def action(session: Session) -> Item:
        space = await session.workspace(ref)
        invitation = await session.client.invitations.create(
            email=email, scope_type="workspace", scope_id=space.id, role=role
        )
        return Item(dump(invitation))

    run(action)
