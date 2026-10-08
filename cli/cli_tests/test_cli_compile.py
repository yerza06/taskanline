"""DSL → грамматика views: имена разрешаются в id запросами к API."""

import json
from typing import Any

import pytest

from cli_tests.conftest import Tkl
from cli_tests.fake_api import BUG, DEV, DONE, PROGRESS, TEAM, TODO, FakeApi


def sent_filters(api: FakeApi) -> dict[str, Any]:
    (request,) = api.sent("POST", "/views/query")
    filters: dict[str, Any] = json.loads(request.content)["filters"]
    return filters


@pytest.mark.parametrize(
    ("dsl", "expected"),
    [
        ("assignee:me", {"assignee_id": {"op": "in", "value": ["@me"]}}),
        ("assignee:dev@example.com,me",
         {"assignee_id": {"op": "in", "value": [DEV, "@me"]}}),
        ("assignee:null", {"assignee_id": {"op": "is_null"}}),
        ("creator:!dev@example.com", {"creator_id": {"op": "nin", "value": [DEV]}}),
        ("team:eng", {"team_id": {"op": "in", "value": [TEAM]}}),
        ('state:"in progress",Done', {"state_id": {"op": "in", "value": [PROGRESS, DONE]}}),
        ("state:!Todo", {"state_id": {"op": "nin", "value": [TODO]}}),
        ("state-type:!completed,!canceled",
         {"state_type": {"op": "nin", "value": ["completed", "canceled"]}}),
        ("label:BUG", {"label_id": {"op": "in", "value": [BUG]}}),
        ("priority:<=2", {"priority": {"op": "lte", "value": 2}}),
        ("priority:urgent,high", {"priority": {"op": "in", "value": [1, 2]}}),
        ("priority:!none", {"priority": {"op": "in", "value": [1, 2, 3, 4]}}),
        ("due:<@today+7d", {"due_date": {"op": "lt", "value": "@today+7d"}}),
        ("due:2026-10-20", {"due_date": {"op": "eq", "value": "2026-10-20"}}),
        ("due:null", {"due_date": {"op": "is_null"}}),
        ("created:>=@week", {"created_at": {"op": "gte", "value": "@start_of_week"}}),
        ("updated:>@today-3d", {"updated_at": {"op": "gt", "value": "@today-3d"}}),
        ("parent:null", {"has_parent": {"op": "eq", "value": False}}),
        ("parent:!null", {"has_parent": {"op": "eq", "value": True}}),
        ("project:null", {"project_id": {"op": "is_null"}}),
        ("title~логин", {"title": {"op": "contains", "value": "логин"}}),
    ],
)  # fmt: skip
def test_dsl_compiles_to_view_grammar(
    tkl: Tkl, api: FakeApi, dsl: str, expected: dict[str, Any]
) -> None:
    result = tkl("task", "list", "--filter", dsl)

    assert result.code == 0, result.err
    assert sent_filters(api) == expected


def test_parent_key_resolves_to_id(tkl: Tkl, api: FakeApi) -> None:
    tkl("task", "list", "--filter", "parent:eng-1")

    assert sent_filters(api) == {
        "parent_id": {"op": "in", "value": ["019a5c1e-0000-7000-8000-000000000001"]}
    }


def test_sort_and_limit(tkl: Tkl, api: FakeApi) -> None:
    tkl("task", "list", "--sort", "-priority", "--limit", "5", "--cursor", "abc")

    (request,) = api.sent("POST", "/views/query")
    body = json.loads(request.content)
    assert (body["sort_by"], body["sort_direction"], body["limit"], body["cursor"]) == (
        "priority",
        "desc",
        5,
        "abc",
    )


@pytest.mark.parametrize(
    ("dsl", "code", "message"),
    [
        ("assignee:ghost@example.com", "user_not_found", "Участник «ghost@example.com»"),
        ("label:nope", "label_not_found", "Доступные: bug"),
        ("team:DES", "team_not_found", "Доступные команды: ENG"),
        ("state:Doing", "state_not_found", "Доступные: Canceled, Done, In Progress, Todo"),
    ],
)
def test_unknown_names_are_4(tkl: Tkl, api: FakeApi, dsl: str, code: str, message: str) -> None:
    result = tkl("task", "list", "--filter", dsl)

    assert result.code == 4
    assert f"[{code}]" in result.err and message in result.err
    assert api.sent("POST", "/views/query") == []


def test_close_picks_first_completed_state(tkl: Tkl, api: FakeApi) -> None:
    result = tkl("task", "close", "ENG-1")

    (patch,) = api.sent("PATCH", "/tasks/019a5c1e-0000-7000-8000-000000000001")
    assert result.code == 0, result.err
    assert json.loads(patch.content) == {"state_id": DONE}


def test_comment_from_stdin(tkl: Tkl, api: FakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("Отчёт агента\n"))

    result = tkl("task", "comment", "019a5c1e-0000-7000-8000-000000000001", "-")

    assert result.code == 0, result.err
    assert json.loads(result.out)["body"] == "Отчёт агента\n"
