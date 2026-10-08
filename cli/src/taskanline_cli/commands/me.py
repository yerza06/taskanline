"""`tkl me`: профиль, свои задачи, входящие уведомления."""

from typing import Annotated

import typer

from taskanline_cli.context import Session, run
from taskanline_cli.filters import STATE_TYPES
from taskanline_cli.output import Item, Listing, col
from taskanline_cli.present import TASK_EXPAND, dump, task_listing

app = typer.Typer(help="Профиль, свои задачи и уведомления", invoke_without_command=True)


@app.callback()
def profile(ctx: typer.Context) -> None:
    """Профиль и список членств."""
    if ctx.invoked_subcommand is not None:
        return

    async def action(session: Session) -> Item:
        return Item(dump(await session.me()), ident="email")

    run(action)


@app.command()
def tasks(
    state_type: Annotated[
        str | None, typer.Option("--state-type", help=", ".join(STATE_TYPES))
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 50,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
) -> None:
    """Задачи, назначенные на меня."""

    async def action(session: Session) -> Listing:
        filters: dict[str, object] = {"assignee_id": {"op": "in", "value": ["@me"]}}
        if state_type:
            filters["state_type"] = {"op": "in", "value": state_type.split(",")}
        workspace = await session.workspace()
        (group,) = (
            await session.client.tasks.query(
                workspace.id, filters=filters, limit=limit, cursor=cursor, expand=TASK_EXPAND
            )
        ).groups
        return task_listing(
            group.items,
            session.settings.web_url,
            next_cursor=group.next_cursor,
            has_more=group.has_more,
            total_hint=group.count,
        )

    run(action)


@app.command()
def inbox(
    unread: Annotated[bool, typer.Option("--unread", help="Только непрочитанные")] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 50,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
) -> None:
    """Уведомления."""

    async def action(session: Session) -> Listing:
        page = await session.client.me.notifications(unread=unread, limit=limit, cursor=cursor)
        return Listing(
            [dump(item) for item in page.items],
            [col("TYPE", "type"), col("TASK", "task_id"), col("AT", "created_at")],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )

    run(action)
