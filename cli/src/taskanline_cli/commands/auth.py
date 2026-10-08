"""`tkl auth`: токен проверяется запросом `GET /me` и только потом сохраняется."""

import typer

from taskanline_cli import config
from taskanline_cli.context import Session, options, run
from taskanline_cli.errors import usage
from taskanline_cli.output import Item, info

app = typer.Typer(help="Вход по токену и проверка доступа", no_args_is_help=True)


def _status(session: Session, me_data: dict[str, object]) -> Item:
    return Item(
        {
            "email": me_data["email"],
            "name": me_data["full_name"],
            "profile": session.settings.profile,
            "api_url": session.settings.api_url,
            "auth_method": me_data["auth_method"],
            "scopes": me_data["scopes"],
        },
        ident="email",
    )


@app.command()
def login() -> None:
    """Проверить токен (--token) и сохранить его в профиль (--profile, --api-url)."""
    opts = options()
    if not opts.token:
        raise usage(
            "token_required", "Нужен --token", "Токен создаётся в веб-интерфейсе: Профиль → Токены"
        )

    async def action(session: Session) -> Item:
        me = await session.client.me.get()
        data = config.load()
        name = session.settings.profile
        profiles = data.setdefault("profiles", {})
        profile = profiles.setdefault(name, {})
        profile["api_url"] = session.settings.api_url
        profile["token"] = opts.token
        data.setdefault("default_profile", name)
        path = config.save(data)
        info(f"Токен сохранён в профиль «{name}» ({path})")
        return _status(session, me.model_dump(mode="json"))

    run(action)


@app.command()
def status() -> None:
    """Текущий пользователь, профиль, адрес API и scope токена."""

    async def action(session: Session) -> Item:
        if not session.settings.token:
            raise usage("token_required", "Токен не задан", "tkl auth login --token …")
        me = await session.client.me.get()
        return _status(session, me.model_dump(mode="json"))

    run(action)


@app.command()
def logout() -> None:
    """Удалить токен из профиля (--profile)."""
    data = config.load()
    name = config.profile_name(data, options().profile)
    profile = data.get("profiles", {}).get(name)
    if not profile or "token" not in profile:
        info(f"В профиле «{name}» токена нет")
        return
    del profile["token"]
    config.save(data)
    info(f"Токен удалён из профиля «{name}»")
