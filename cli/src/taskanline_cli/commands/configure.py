"""`tkl config`: значения текущего профиля; токены в выводе замаскированы."""

from typing import Annotated

import typer

from taskanline_cli import config
from taskanline_cli.context import options
from taskanline_cli.errors import not_found, usage
from taskanline_cli.output import Item, render

app = typer.Typer(help="Конфигурация и профили", no_args_is_help=True)

KEYS = (*config.PROFILE_KEYS, "default_profile")


def _check(key: str) -> None:
    if key not in KEYS:
        raise usage("unknown_config_key", f"Неизвестный ключ «{key}»", f"Ключи: {', '.join(KEYS)}")


def _show(data: dict[str, object]) -> None:
    render(Item(data, ident="profile"), options().format)


@app.command("list")
def list_() -> None:
    """Показать конфигурацию."""
    data = config.load()
    profiles = {
        name: {
            key: config.mask(str(value)) if key == "token" else value
            for key, value in profile.items()
        }
        for name, profile in data.get("profiles", {}).items()
    }
    _show(
        {
            "path": str(config.config_path()),
            "default_profile": data.get("default_profile"),
            "profile": config.profile_name(data, options().profile),
            "profiles": profiles,
        }
    )


@app.command("set")
def set_(
    key: Annotated[str, typer.Argument(help="api_url, token, workspace, team, web_url")],
    value: Annotated[str, typer.Argument()],
) -> None:
    """Установить значение в текущем профиле, например: tkl config set team ENG."""
    _check(key)
    data = config.load()
    if key == "default_profile":
        data["default_profile"] = value
    else:
        name = config.profile_name(data, options().profile)
        data.setdefault("profiles", {}).setdefault(name, {})[key] = value
    config.save(data)


@app.command("get")
def get(key: Annotated[str, typer.Argument()]) -> None:
    """Прочитать значение из текущего профиля."""
    _check(key)
    data = config.load()
    if key == "default_profile":
        value = data.get("default_profile")
    else:
        name = config.profile_name(data, options().profile)
        value = data.get("profiles", {}).get(name, {}).get(key)
    if value is None:
        raise not_found("config_key_unset", f"Значение «{key}» не задано")
    typer.echo(value)


@app.command("path")
def path() -> None:
    """Путь к файлу конфигурации."""
    typer.echo(str(config.config_path()))
