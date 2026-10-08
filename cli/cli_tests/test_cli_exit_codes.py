"""Коды выхода 0–7: каждое исключение SDK и каждая ошибка использования."""

import httpx
import pytest

from cli_tests.conftest import Tkl
from cli_tests.fake_api import FakeApi, error


@pytest.mark.parametrize(
    ("status", "code", "exit_code"),
    [
        (400, "invalid_filter", 2),
        (422, "validation_error", 2),
        (500, "internal", 2),
        (401, "not_authenticated", 3),
        (403, "insufficient_role", 3),
        (404, "task_not_found", 4),
        (409, "task_key_ambiguous", 5),
        (429, "rate_limited", 6),
    ],
)
def test_api_errors(tkl: Tkl, api: FakeApi, status: int, code: str, exit_code: int) -> None:
    api.routes[("GET", "/tasks/ENG-1")] = error(status, code, "Текст", **{"Retry-After": "9"})

    result = tkl("task", "show", "ENG-1")

    assert result.code == exit_code
    assert f"Ошибка [{code}]" in result.err
    assert result.out == ""


def test_rate_limit_reports_retry_after(tkl: Tkl, api: FakeApi) -> None:
    api.routes[("GET", "/tasks/ENG-1")] = error(
        429, "rate_limited", "Много", **{"Retry-After": "9"}
    )

    assert "Повторите через 9 с" in tkl("task", "show", "ENG-1").err


def test_network_failure_is_7(tkl: Tkl, api: FakeApi) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    api.routes[("GET", "/tasks/ENG-1")] = down

    assert tkl("task", "show", "ENG-1").code == 7


def test_missing_task_names_teams(tkl: Tkl) -> None:
    result = tkl("task", "show", "ENG-999")

    assert result.code == 4
    assert result.err == (
        "Ошибка [task_not_found]: Задача ENG-999 не найдена.\n"
        "Доступные команды: ENG. Проверьте ключ или tkl task list\n"
    )


def test_read_token_hint(tkl: Tkl, api: FakeApi) -> None:
    api.routes[("POST", "/tasks/019a5c1e-0000-7000-8000-000000000001/comments")] = error(
        403, "insufficient_scope", "Токен только на чтение"
    )

    result = tkl("task", "comment", "019a5c1e-0000-7000-8000-000000000001", "-m", "x")

    assert result.code == 3
    assert "нужен токен read_write" in result.err


@pytest.mark.parametrize(
    "args",
    [
        ("task", "frobnicate"),
        ("task", "list", "--limit", "zero"),
        ("task", "move", "ENG-1"),
        ("task", "list", "--sort", "random"),
        ("config", "set", "colour", "red"),
    ],
)
def test_usage_errors_are_1(tkl: Tkl, api: FakeApi, args: tuple[str, ...]) -> None:
    result = tkl(*args)

    assert result.code == 1, result.err
    assert api.requests == []


def test_filter_error_before_any_request(tkl: Tkl, api: FakeApi) -> None:
    result = tkl("task", "list", "--filter", "assignee:me asignee:you")

    assert result.code == 1
    assert "на позиции 12" in result.err and "assignee" in result.err
    assert api.requests == []


def test_unknown_state_is_not_found_with_choices(tkl: Tkl) -> None:
    result = tkl("task", "state", "ENG-1", "In Progres")

    assert result.code == 4
    assert "Возможно: In Progress" in result.err
    assert "Todo, In Progress, Done, Canceled" in result.err


def test_help_is_0(tkl: Tkl) -> None:
    result = tkl("task", "--help")

    assert result.code == 0
    assert "list" in result.out
