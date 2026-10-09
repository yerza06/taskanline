"""`tkl-mcp`: запуск сервера в stdio или streamable HTTP.

stdio — процесс-потомок локального клиента (Claude Desktop, Claude Code), токен — из
`--token`, окружения или профиля. HTTP — один процесс для многих пользователей, поэтому
токен каждого приходит заголовком `Authorization: Bearer`, а токен процесса не берётся.
"""

import argparse
import sys

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from taskanline_mcp import __version__, config
from taskanline_mcp.server import build


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tkl-mcp", description="MCP-сервер TasKanLine")
    p.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    p.add_argument("--api-url", help="Адрес API (иначе TKL_API_URL или профиль)")
    p.add_argument("--token", help="PAT для stdio (иначе TKL_TOKEN или профиль)")
    p.add_argument("--profile", help="Профиль общего с tkl конфига")
    p.add_argument("--read-only", action="store_true", help="Без инструментов записи")
    p.add_argument("--workspace", help="Ограничить сервер одним рабочим пространством")
    p.add_argument(
        "--max-items", type=int, default=config.HARD_MAX_ITEMS, help="Потолок списков, ≤ 50"
    )
    p.add_argument("--host", default="127.0.0.1", help="HTTP: адрес прослушивания")
    p.add_argument("--port", type=int, default=8765, help="HTTP: порт")
    p.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help="HTTP: допустимый заголовок Host за прокси (повторяемый), например mcp.example.com",
    )
    p.add_argument("--version", action="version", version=f"tkl-mcp {__version__}")
    return p


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    http = args.transport == "http"
    settings = config.resolve(
        profile=args.profile,
        api_url=args.api_url,
        token=args.token,
        workspace=args.workspace,
        read_only=args.read_only,
        max_items=args.max_items,
        token_from_header=http,
    )
    server = build(settings)
    if not http:
        if not settings.token:
            sys.stderr.write("tkl-mcp: токен не задан — --token, TKL_TOKEN или tkl auth login\n")
        server.run("stdio")
        return
    # Защита от DNS rebinding: Host — только локальный и явно разрешённые за прокси.
    hosts = [f"{args.host}:{args.port}", f"localhost:{args.port}", *args.allowed_host]
    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=hosts),
        host=args.host,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
