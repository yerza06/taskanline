"""Конфиг: файл 0600, приоритет источников, маскировка токена, контекст по умолчанию."""

import json
import stat
import tomllib
from pathlib import Path

import pytest

from cli_tests.conftest import Tkl
from cli_tests.fake_api import TEAM, FakeApi
from taskanline_cli import config


def test_login_writes_private_profile(tkl: Tkl, config_home: Path) -> None:
    result = tkl("auth", "login", "--token", "tkl_brand_new", "--profile", "work")

    path = config_home / "taskanline" / "config.toml"
    data = tomllib.loads(path.read_text())
    assert result.code == 0, result.err
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert data == {
        "default_profile": "work",
        "profiles": {"work": {"api_url": "http://tkl.test", "token": "tkl_brand_new"}},
    }


def test_login_checks_token_first(tkl: Tkl, api: FakeApi, config_home: Path) -> None:
    from cli_tests.fake_api import error

    api.routes[("GET", "/me")] = error(401, "invalid_token", "Токен недействителен")

    result = tkl("auth", "login", "--token", "tkl_wrong")

    assert result.code == 3
    assert not (config_home / "taskanline" / "config.toml").exists()


def test_precedence_option_env_profile_default(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config.save({"profiles": {"default": {"api_url": "http://profile", "team": "ENG"}}})
    monkeypatch.delenv("TKL_API_URL", raising=False)

    assert config.resolve().api_url == "http://profile"
    monkeypatch.setenv("TKL_API_URL", "http://env")
    assert config.resolve().api_url == "http://env"
    assert config.resolve(api_url="http://option").api_url == "http://option"
    assert config.resolve().team == "ENG"
    config.save({})
    monkeypatch.delenv("TKL_API_URL")
    assert config.resolve().api_url == config.DEFAULT_API_URL


def test_config_set_get_list(tkl: Tkl) -> None:
    tkl("auth", "login", "--token", "tkl_7fa3c1deadbeef")
    tkl("config", "set", "team", "ENG")

    got = tkl("config", "get", "team")
    listed = json.loads(tkl("config", "list").out)

    assert got.out == "ENG\n"
    assert listed["profiles"]["default"]["token"] == "tkl_7fa3…"
    assert "deadbeef" not in json.dumps(listed)


def test_logout_removes_token(tkl: Tkl) -> None:
    tkl("auth", "login", "--token", "tkl_7fa3c1deadbeef")

    tkl("auth", "logout")

    assert "token" not in config.load()["profiles"]["default"]


def test_team_from_profile_scopes_list_and_all_teams_lifts_it(
    tkl: Tkl, api: FakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TKL_TEAM", "ENG")

    tkl("task", "list")
    tkl("task", "list", "--all-teams")

    scoped, unscoped = (json.loads(r.content)["filters"] for r in api.sent("POST", "/views/query"))
    assert scoped == {"team_id": {"op": "in", "value": [TEAM]}}
    assert unscoped == {}
