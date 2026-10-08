"""Конфигурация `tkl`: файл профилей и порядок источников.

Приоритет, от высшего к низшему: опция командной строки → переменная окружения →
профиль из конфига → значение по умолчанию. Файл создаётся с правами `0600`: токен в
нём лежит открытым текстом (CLI-спека §4).
"""

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_PROFILE = "default"
# Что можно хранить в профиле — `tkl config set` принимает только эти ключи.
PROFILE_KEYS = ("api_url", "token", "workspace", "team", "web_url")
ENV = {
    "api_url": "TKL_API_URL",
    "token": "TKL_TOKEN",
    "workspace": "TKL_WORKSPACE",
    "team": "TKL_TEAM",
}


class ConfigError(Exception):
    """Конфиг не читается или ключ неизвестен — ошибка использования."""


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "taskanline" / "config.toml"


def load() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Не читается конфиг {path}: {error}") from error


def _string(value: str) -> str:
    # Базовая строка TOML понимает те же экранирования, что и JSON.
    return json.dumps(value, ensure_ascii=False)


def dump(data: dict[str, Any]) -> str:
    lines = []
    if "default_profile" in data:
        lines.append(f"default_profile = {_string(data['default_profile'])}")
    for name, profile in data.get("profiles", {}).items():
        lines.append("")
        lines.append(f"[profiles.{_string(name)}]")
        lines.extend(f"{key} = {_string(str(value))}" for key, value in profile.items())
    return "\n".join(lines).lstrip("\n") + "\n"


def save(data: dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Права выставляются до записи: токен ни мгновения не лежит в файле, открытом всем.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(dump(data))
    path.chmod(0o600)
    return path


def profile_name(data: dict[str, Any], explicit: str | None) -> str:
    return (
        explicit
        or os.environ.get("TKL_PROFILE")
        or data.get("default_profile")
        or (DEFAULT_PROFILE)
    )


@dataclass(frozen=True)
class Settings:
    profile: str
    api_url: str
    token: str | None
    workspace: str | None
    team: str | None
    web_url: str
    timeout: float


def resolve(
    *,
    profile: str | None = None,
    api_url: str | None = None,
    token: str | None = None,
    timeout: float = 30.0,
) -> Settings:
    data = load()
    name = profile_name(data, profile)
    stored: dict[str, Any] = data.get("profiles", {}).get(name, {})
    explicit = {"api_url": api_url, "token": token}

    def pick(key: str) -> str | None:
        value = explicit.get(key) or os.environ.get(ENV.get(key, "")) or stored.get(key)
        return str(value) if value else None

    resolved_api = (pick("api_url") or DEFAULT_API_URL).rstrip("/")
    web = str(stored.get("web_url") or resolved_api.removesuffix("/api/v1"))
    return Settings(
        profile=name,
        api_url=resolved_api,
        token=pick("token"),
        workspace=pick("workspace"),
        team=pick("team"),
        web_url=web.rstrip("/"),
        timeout=timeout,
    )


def mask(token: str) -> str:
    """`tkl_7fa3c1…` — видно, какой токен, но не сам токен."""
    return token[:8] + "…" if len(token) > 8 else "…"
