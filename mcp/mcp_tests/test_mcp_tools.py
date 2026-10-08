"""Инструменты: параметры → вызовы SDK, потолки, тексты ошибок."""

import json
from typing import Any

import httpx
from mcp.types import CallToolResult, TextContent

from cli_tests.fake_api import BUG, DEV, DONE, PROGRESS, TASK_ID, TEAM, FakeApi, error, task
from mcp_tests.conftest import Connect


def text(result: CallToolResult) -> str:
    (content,) = result.content
    assert isinstance(content, TextContent)
    return content.text


def sent_query(api: FakeApi) -> dict[str, Any]:
    (request,) = api.sent("POST", "/views/query")
    body: dict[str, Any] = json.loads(request.content)
    return body


class TestSearch:
    async def test_without_filters_only_open_tasks(self, connect: Connect, api: FakeApi) -> None:
        async with connect() as client:
            result = await client.call_tool("search_tasks", {})

        assert not result.is_error, text(result)
        assert sent_query(api)["filters"] == {
            "state_type": {"op": "in", "value": ["unstarted", "started"]}
        }
        assert result.structured_content == {
            "tasks": [
                {
                    "key": "ENG-1",
                    "title": "Починить логин",
                    "state": "Todo",
                    "state_type": "unstarted",
                    "assignee": "agent@example.com",
                    "priority": "high",
                    "due_date": "2026-10-20",
                    "labels": ["bug"],
                    "project": None,
                    "description": "Редирект теряет query",
                    "url": "http://tkl.test/ENG-1",
                }
            ],
            "total": 1,
            "has_more": False,
            "next_cursor": None,
        }

    async def test_filters_resolve_names(self, connect: Connect, api: FakeApi) -> None:
        async with connect() as client:
            await client.call_tool(
                "search_tasks",
                {
                    "team": "eng",
                    "assignee": "dev@example.com",
                    "label": ["bug"],
                    "state_type": ["started"],
                    "priority": "urgent",
                    "due_before": "today+7d",
                    "query": "логин",
                },
            )

        assert sent_query(api)["filters"] == {
            "team_id": {"op": "in", "value": [TEAM]},
            "title": {"op": "contains", "value": "логин"},
            "assignee_id": {"op": "in", "value": [DEV]},
            "label_id": {"op": "in", "value": [BUG]},
            "priority": {"op": "in", "value": [1]},
            "due_date": {"op": "lt", "value": "@today+7d"},
            "state_type": {"op": "in", "value": ["started"]},
        }

    async def test_max_items_caps_the_page(self, connect: Connect, api: FakeApi) -> None:
        async with connect(max_items=10) as client:
            await client.call_tool("search_tasks", {"limit": 50})

        assert sent_query(api)["limit"] == 10

    async def test_long_description_is_clipped(self, connect: Connect, api: FakeApi) -> None:
        long = {"key": None, "count": 1, "next_cursor": None, "has_more": False,
                "items": [task(description="д" * 5000)]}  # fmt: skip
        api.routes[("POST", "/views/query")] = httpx.Response(
            200, json={"group_by": None, "groups": [long]}
        )

        async with connect() as client:
            result = await client.call_tool("search_tasks", {})

        assert result.structured_content is not None
        description = result.structured_content["tasks"][0]["description"]
        assert len(description) == 200 and description.endswith("…")


class TestGetTask:
    async def test_card_with_last_twenty_comments(self, connect: Connect, api: FakeApi) -> None:
        comment: dict[str, Any] = {"task_id": TASK_ID, "author_id": DEV, "author_token_id": None,
                   "parent_id": None, "mention_ids": [], "created_at": "2026-10-08T10:00:00Z",
                   "updated_at": "2026-10-08T10:00:00Z"}  # fmt: skip
        comments = [
            {**comment, "id": f"019a5c1e-0000-7000-8000-{n:012d}", "body": f"#{n}"}
            for n in range(30)
        ]
        api.routes[("GET", f"/tasks/{TASK_ID}/comments")] = httpx.Response(
            200, json={"items": comments, "next_cursor": None, "has_more": False}
        )
        api.routes[("GET", f"/tasks/{TASK_ID}/subtasks")] = httpx.Response(200, json={"items": []})

        async with connect() as client:
            result = await client.call_tool("get_task", {"key": "eng-1"})

        card = result.structured_content
        assert card is not None, text(result)
        assert card["key"] == "ENG-1" and card["description"] == "Редирект теряет query"
        assert card["comments_total"] == 30
        assert [c["body"] for c in card["comments"]] == [f"#{n}" for n in range(10, 30)]
        assert card["comments"][0]["author"] == "dev@example.com"
        assert card["subtasks"] == []
        assert "relations" not in card

    async def test_missing_task_names_teams(self, connect: Connect) -> None:
        async with connect() as client:
            result = await client.call_tool("get_task", {"key": "ENG-999", "include": []})

        assert result.is_error
        assert text(result) == "Задача ENG-999 не найдена. Доступные команды: ENG."


class TestWrite:
    async def test_state_by_name(self, connect: Connect, api: FakeApi) -> None:
        async with connect() as client:
            result = await client.call_tool(
                "update_task_state", {"key": "ENG-1", "state": "in progress"}
            )

        (patch,) = api.sent("PATCH", f"/tasks/{TASK_ID}")
        assert json.loads(patch.content) == {"state_id": PROGRESS}
        assert not result.is_error

    async def test_unknown_state_lists_choices(self, connect: Connect) -> None:
        async with connect() as client:
            result = await client.call_tool(
                "update_task_state", {"key": "ENG-1", "state": "Готово"}
            )

        assert result.is_error
        assert text(result) == (
            "Статус «Готово» не существует в команде ENG. "
            "Доступные: Todo, In Progress, Done, Canceled."
        )

    async def test_update_clears_only_listed_fields(self, connect: Connect, api: FakeApi) -> None:
        async with connect() as client:
            await client.call_tool(
                "update_task",
                {"key": "ENG-1", "priority": "low", "clear": ["due_date", "assignee"]},
            )
            both = await client.call_tool(
                "update_task", {"key": "ENG-1", "due_date": "2026-11-01", "clear": ["due_date"]}
            )
            nothing = await client.call_tool("update_task", {"key": "ENG-1"})

        (patch,) = api.sent("PATCH", f"/tasks/{TASK_ID}")
        assert json.loads(patch.content) == {"due_date": None, "assignee_id": None, "priority": 4}
        assert both.is_error and "clear" in text(both)
        assert nothing.is_error and "Нечего менять" in text(nothing)

    async def test_create_with_labels_and_state(self, connect: Connect, api: FakeApi) -> None:
        api.routes[("POST", "/tasks")] = httpx.Response(201, json=task(key="ENG-2"))

        async with connect() as client:
            result = await client.call_tool(
                "create_task",
                {"title": "Новая", "state": "Done", "labels": ["bug"], "assignee": "me"},
            )

        (post,) = api.sent("POST", "/tasks")
        assert json.loads(post.content) == {
            "title": "Новая",
            "team_id": TEAM,
            "state_id": DONE,
            "label_ids": [BUG],
            "assignee_id": "019a5c1e-0000-7000-8000-0000000000d1",
        }
        assert "Idempotency-Key" in post.headers
        assert result.structured_content is not None
        assert result.structured_content["created"]["url"] == "http://tkl.test/ENG-2"

    async def test_unknown_label_is_not_created(self, connect: Connect, api: FakeApi) -> None:
        async with connect() as client:
            result = await client.call_tool("create_task", {"title": "x", "labels": ["urgent!"]})

        assert result.is_error
        assert "Метка «urgent!» не найдена" in text(result)
        assert api.sent("POST", "/tasks") == []


class TestErrors:
    async def test_messages_with_hints(self, connect: Connect, api: FakeApi) -> None:
        cases = {
            error(403, "insufficient_scope"): "Токен выдан только на чтение. Изменения недоступны.",
            error(403, "insufficient_role"): "Недостаточно прав для этого действия. "
            "Обратитесь к администратору рабочего пространства.",
            error(429, "rate_limited", **{"Retry-After": "30"}): "Превышен лимит запросов. "
            "Повторите через 30 секунд.",
            error(401, "invalid_token"): "Токен не принят: он отозван, истёк или не передан. "
            "Проверьте TKL_TOKEN или заголовок Authorization: Bearer.",
        }
        for response, message in cases.items():
            api.routes[("POST", f"/tasks/{TASK_ID}/comments")] = response
            async with connect() as client:
                result = await client.call_tool("comment_task", {"key": "ENG-1", "body": "x"})
            assert (result.is_error, text(result)) == (True, message)

    async def test_network_down(self, connect: Connect, api: FakeApi) -> None:
        def down(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        api.routes[("GET", "/workspaces")] = down

        async with connect() as client:
            result = await client.call_tool("list_teams", {})

        assert text(result) == (
            "Сервер TasKanLine не отвечает. Проверьте TKL_API_URL и доступность сети."
        )


class TestWorkspaceRestriction:
    async def test_other_workspaces_are_invisible(self, connect: Connect, api: FakeApi) -> None:
        async with connect(workspace="other") as client:
            spaces = await client.call_tool("list_workspaces", {})
            teams = await client.call_tool("list_teams", {"workspace": "acme"})

        assert spaces.structured_content == {"workspaces": []}
        assert teams.is_error and "Workspace «acme» не найден" in text(teams)

    async def test_restricted_workspace_works(self, connect: Connect) -> None:
        async with connect(workspace="acme") as client:
            spaces = await client.call_tool("list_workspaces", {})
            teams = await client.call_tool("list_teams", {})

        assert spaces.structured_content is not None
        assert [s["slug"] for s in spaces.structured_content["workspaces"]] == ["acme"]
        assert spaces.structured_content["workspaces"][0]["role"] == "member"
        assert teams.structured_content is not None
        assert teams.structured_content["teams"][0]["states"][1] == {
            "name": "In Progress",
            "type": "started",
        }


async def test_http_mode_requires_bearer(connect: Connect) -> None:
    async with connect(token=None, token_from_header=True) as client:
        result = await client.call_tool("list_teams", {})

    assert result.is_error
    assert "Authorization: Bearer" in text(result)
