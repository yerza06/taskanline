"""Форматы вывода, разделение потоков и стабильность JSON-контракта."""

import json
import sys

import pytest

from cli_tests.conftest import Tkl
from cli_tests.fake_api import TASK_ID, FakeApi, error
from taskanline_cli.output import Format, choose_format

COMPACT_TASK = {
    "key": "ENG-1",
    "title": "Починить логин",
    "state": {"name": "Todo", "type": "unstarted"},
    "assignee": {"email": "agent@example.com", "name": "Агент"},
    "priority": "high",
    "due_date": "2026-10-20",
    "labels": ["bug"],
    "project": None,
    "url": "http://tkl.test/ENG-1",
}


class TestFormatChoice:
    def test_terminal_gets_table_pipe_gets_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TKL_OUTPUT", raising=False)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        assert choose_format(explicit=None, json_flag=False, quiet=False) == Format.TABLE
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        assert choose_format(explicit=None, json_flag=False, quiet=False) == Format.JSON

    def test_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setenv("TKL_OUTPUT", "plain")
        assert choose_format(explicit=None, json_flag=False, quiet=False) == Format.PLAIN
        assert choose_format(explicit=None, json_flag=True, quiet=False) == Format.JSON
        assert choose_format(explicit="table", json_flag=True, quiet=False) == Format.TABLE
        assert choose_format(explicit="table", json_flag=True, quiet=True) == Format.QUIET


class TestContract:
    """Снимки JSON: изменение схемы вывода обязано ломать эти тесты."""

    def test_task_list_snapshot(self, tkl: Tkl) -> None:
        result = tkl("task", "list")

        assert result.code == 0, result.err
        assert json.loads(result.out) == {
            "items": [COMPACT_TASK],
            "next_cursor": None,
            "has_more": False,
            "total_hint": 1,
        }

    def test_task_show_snapshot(self, tkl: Tkl) -> None:
        result = tkl("task", "show", "ENG-1")

        assert json.loads(result.out) == {
            **COMPACT_TASK,
            "id": TASK_ID,
            "description": "Редирект теряет query",
            "creator": {"email": "dev@example.com", "name": "Dev"},
            "parent": None,
            "relations": [],
            "started_at": None,
            "completed_at": None,
            "created_at": "2026-10-08T10:00:00+00:00",
            "updated_at": "2026-10-08T10:00:00+00:00",
            "deleted_at": None,
        }

    def test_global_flags_work_after_the_command(self, tkl: Tkl) -> None:
        quiet = tkl("task", "list", "-q")
        plain = tkl("task", "list", "--output", "plain")

        assert quiet.out == "ENG-1\n"
        assert plain.out == "ENG-1\tTodo\thigh\tПочинить логин\tagent@example.com\n"

    def test_table_is_human_readable(self, tkl: Tkl) -> None:
        result = tkl("--output=table", "--no-color", "task", "list")

        assert "ENG-1" in result.out and "Починить логин" in result.out
        assert "KEY" in result.out


class TestStreams:
    def test_error_leaves_stdout_empty(self, tkl: Tkl, api: FakeApi) -> None:
        api.routes[("POST", "/views/query")] = error(500, "internal", "Сломалось")

        result = tkl("task", "list")

        assert result.out == ""
        assert result.err.startswith("Ошибка [internal]: Сломалось")

    def test_info_messages_go_to_stderr(self, tkl: Tkl) -> None:
        result = tkl("auth", "login", "--token", "tkl_new_token")

        assert result.code == 0, result.err
        assert json.loads(result.out)["email"] == "agent@example.com"
        assert "Токен сохранён" in result.err
