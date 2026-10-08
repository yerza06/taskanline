"""Транспорт stdio: настоящий процесс `tkl-mcp`, как его запускает Claude Desktop.

API в этом тесте недоступен намеренно: проверяется протокол и то, что сбой сети приходит
модели понятным текстом, а не обрывом процесса.
"""

import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.types import TextContent


async def test_stdio_round_trip(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "taskanline_mcp", "--read-only"],
        env={
            "TKL_API_URL": "http://127.0.0.1:9",
            "TKL_TOKEN": "tkl_stdio",
            "XDG_CONFIG_HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        },
    )

    async with Client(params) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        result = await client.call_tool("list_teams", {})

    assert "search_tasks" in names and "create_task" not in names
    assert result.is_error
    (content,) = result.content
    assert isinstance(content, TextContent)
    assert content.text.startswith("Сервер TasKanLine не отвечает")
