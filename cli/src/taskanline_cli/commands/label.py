"""`tkl label`: метки команды и workspace."""

from typing import Annotated

import typer

from taskanline_cli.commands import Team, Workspace
from taskanline_cli.context import Session, run
from taskanline_cli.output import Item, Listing, col
from taskanline_cli.present import dump, listing

app = typer.Typer(help="Метки", no_args_is_help=True)


@app.command("list")
def list_(team: Team = None, workspace: Workspace = None) -> None:
    """Метки: общие для workspace и метки команды."""

    async def action(session: Session) -> Listing:
        space = await session.workspace(workspace)
        chosen = await session.default_team(team)
        labels = await session.client.labels.all(space.id, team_id=chosen.id if chosen else None)
        return listing(labels, [col("NAME", "name"), col("COLOR", "color"), col("ID", "id")])

    run(action)


@app.command()
def create(
    name: Annotated[str, typer.Option("--name")],
    color: Annotated[str, typer.Option("--color", help='Например "#ff0000"')],
    team: Team = None,
    workspace: Workspace = None,
) -> None:
    """Создать метку; без --team — общую для workspace."""

    async def action(session: Session) -> Item:
        space = await session.workspace(workspace)
        owner = await session.team(team) if team else None
        created = await session.client.labels.create(
            space.id, name=name, color=color, team_id=owner.id if owner else None
        )
        return Item(dump(created))

    run(action)


@app.command()
def delete(label_id: Annotated[str, typer.Argument(metavar="ID")]) -> None:
    """Удалить метку."""

    async def action(session: Session) -> Item:
        await session.client.labels.delete(label_id)
        return Item({"id": label_id, "deleted": True})

    run(action)
