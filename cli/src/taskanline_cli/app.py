"""Корневое приложение `tkl`: глобальные опции, группы команд, коды выхода.

Глобальные опции принимаются в любом месте строки: `tkl task list --json` так же, как
`tkl --json task list`. Агенту естественнее дописать флаг в конец, а Click понимает
опции группы только до подкоманды — поэтому `main()` переносит их вперёд сам.
"""

import logging
import sys
from typing import Annotated

import typer

from taskanline_cli import __version__
from taskanline_cli.commands import auth, configure, label, me, project, task, team, view, workspace
from taskanline_cli.config import ConfigError
from taskanline_cli.context import Options, set_options
from taskanline_cli.errors import CliError, ExitCode, describe, exit_code_for
from taskanline_cli.filters import FilterSyntaxError
from taskanline_cli.output import Format
from taskanline_sdk import TasKanLineError

app = typer.Typer(
    name="tkl",
    help="TasKanLine из терминала. Вывод — JSON, если stdout не терминал.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(auth.app, name="auth")
app.add_typer(configure.app, name="config")
app.add_typer(me.app, name="me")
app.add_typer(workspace.app, name="workspace")
app.add_typer(workspace.app, name="ws", hidden=True)
app.add_typer(team.app, name="team")
app.add_typer(project.app, name="project")
app.add_typer(task.app, name="task")
app.add_typer(view.app, name="view")
app.add_typer(label.app, name="label")

CLICK_USAGE_ERROR = 2
FLAGS = frozenset({"--json", "--quiet", "-q", "--no-color", "--verbose", "-v"})
VALUED = frozenset({"--output", "--profile", "--api-url", "--token", "--timeout"})


def _version(value: bool) -> None:
    if value:
        opts = Options()
        settings = opts.settings()
        sys.stdout.write(f"tkl {__version__}\nAPI: {settings.api_url}\n")
        raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    json_flag: Annotated[bool, typer.Option("--json", help="Принудительно JSON")] = False,
    output: Annotated[Format | None, typer.Option("--output", help="Формат вывода")] = None,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Только идентификаторы, по одному на строку")
    ] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="Без ANSI-цвета")] = False,
    profile: Annotated[str | None, typer.Option("--profile", help="Профиль конфига")] = None,
    api_url: Annotated[str | None, typer.Option("--api-url", help="Адрес API")] = None,
    token: Annotated[str | None, typer.Option("--token", help="Токен доступа")] = None,
    timeout: Annotated[float, typer.Option("--timeout", help="Таймаут запроса, с")] = 30.0,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Запросы в stderr")] = False,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Версия и адрес API"),
    ] = False,
) -> None:
    set_options(
        Options(
            output=output.value if output else None,
            json_flag=json_flag,
            quiet=quiet,
            no_color=no_color,
            profile=profile,
            api_url=api_url,
            token=token,
            timeout=timeout,
            verbose=verbose,
        )
    )
    if verbose:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")
        logging.getLogger("httpx").setLevel(logging.INFO)


def hoist(argv: list[str]) -> list[str]:
    """Глобальные опции — вперёд, остальное в прежнем порядке. После `--` не трогаем."""
    front: list[str] = []
    rest: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            rest.extend(argv[index:])
            break
        name = arg.split("=", 1)[0]
        if arg in FLAGS:
            front.append(arg)
        elif name in VALUED:
            front.append(arg)
            if "=" not in arg and index + 1 < len(argv):
                index += 1
                front.append(argv[index])
        else:
            rest.append(arg)
        index += 1
    return front + rest


def _fail(text: str, code: ExitCode) -> int:
    sys.stderr.write(text.rstrip("\n") + "\n")
    return int(code)


def main(argv: list[str] | None = None) -> int:
    args = hoist(list(sys.argv[1:] if argv is None else argv))
    set_options(Options())
    command = typer.main.get_command(app)
    try:
        # Ошибки разбора аргументов Click печатает сам и выходит с 2; по спеке это 1.
        # Наши исключения Click не трогает — они долетают до обработчиков ниже.
        command.main(args=args, prog_name="tkl", standalone_mode=True)
    except SystemExit as stop:
        code = stop.code if isinstance(stop.code, int) else 1
        return int(ExitCode.USAGE) if code == CLICK_USAGE_ERROR else code
    except FilterSyntaxError as error:
        return _fail(error.render(), ExitCode.USAGE)
    except ConfigError as error:
        return _fail(f"Ошибка [config_error]: {error}", ExitCode.USAGE)
    except CliError as error:
        text = f"Ошибка [{error.code}]: {error.message}."
        return _fail(text + (f"\n{error.hint}" if error.hint else ""), error.exit_code)
    except TasKanLineError as error:
        return _fail(describe(error), exit_code_for(error))
    return 0


def entry() -> None:
    sys.exit(main())
