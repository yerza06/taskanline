"""Настройки сервера: ключи запуска → окружение → профиль общего с CLI конфига.

Файл тот же, что у `tkl` (`~/.config/taskanline/config.toml`): один `tkl auth login`
настраивает оба инструмента. Модуль только читает его — запись остаётся за CLI.
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_API_URL = "http://localhost:8000"
# Жёсткий потолок списков: выше не поднимается ни ключом запуска, ни параметром инструмента.
HARD_MAX_ITEMS = 50


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "taskanline" / "config.toml"


def _load() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SystemExit(f"Не читается конфиг {path}: {error}") from error


@dataclass(frozen=True)
class Settings:
    api_url: str
    token: str | None
    workspace: str | None
    web_url: str
    read_only: bool = False
    max_items: int = HARD_MAX_ITEMS
    # HTTP-режим: токен приходит заголовком от каждого клиента, токен процесса не годится.
    token_from_header: bool = False


def resolve(
    *,
    profile: str | None = None,
    api_url: str | None = None,
    token: str | None = None,
    workspace: str | None = None,
    read_only: bool = False,
    max_items: int = HARD_MAX_ITEMS,
    token_from_header: bool = False,
) -> Settings:
    data = _load()
    name = profile or os.environ.get("TKL_PROFILE") or data.get("default_profile") or "default"
    stored: dict[str, Any] = data.get("profiles", {}).get(name, {})

    def pick(explicit: str | None, env: str, key: str) -> str | None:
        value = explicit or os.environ.get(env) or stored.get(key)
        return str(value) if value else None

    resolved_api = (pick(api_url, "TKL_API_URL", "api_url") or DEFAULT_API_URL).rstrip("/")
    web = str(stored.get("web_url") or resolved_api.removesuffix("/api/v1")).rstrip("/")
    return Settings(
        api_url=resolved_api,
        token=None if token_from_header else pick(token, "TKL_TOKEN", "token"),
        workspace=pick(workspace, "TKL_WORKSPACE", "workspace"),
        web_url=web,
        read_only=read_only,
        max_items=max(1, min(max_items, HARD_MAX_ITEMS)),
        token_from_header=token_from_header,
    )
