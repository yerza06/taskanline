"""Ресурсы SDK: пути, тела запросов, модели ответов и пагинация."""

import json
from typing import Any

import httpx

from sdk_tests.fake import TASK, Fake


def page(items: list[dict[str, Any]], cursor: str | None = None) -> dict[str, Any]:
    group = {
        "key": None,
        "count": 3,
        "items": items,
        "next_cursor": cursor,
        "has_more": bool(cursor),
    }
    return {"group_by": None, "groups": [group]}


async def test_query_sends_view_grammar() -> None:
    fake = Fake(httpx.Response(200, json=page([TASK])))

    async with fake.client() as client:
        result = await client.tasks.query(
            "ws",
            filters={"assignee_id": {"op": "in", "value": ["@me"]}},
            sort_by="priority",
            limit=5,
            expand=["state"],
        )

    (request,) = fake.requests
    assert (request.method, request.url.path) == ("POST", "/api/v1/views/query")
    assert request.url.params["expand"] == "state"
    assert json.loads(request.content) == {
        "workspace_id": "ws",
        "filters": {"assignee_id": {"op": "in", "value": ["@me"]}},
        "sort_by": "priority",
        "sort_direction": "asc",
        "group_by": None,
        "group": None,
        "cursor": None,
        "limit": 5,
    }
    assert result.groups[0].items[0].key == "ENG-1"


async def test_iter_query_follows_cursor() -> None:
    second = {**TASK, "id": "019a5c1e-0000-7000-8000-000000000002", "key": "ENG-2"}
    third = {**TASK, "id": "019a5c1e-0000-7000-8000-000000000003", "key": "ENG-3"}
    fake = Fake(
        httpx.Response(200, json=page([TASK, second], cursor="c1")),
        httpx.Response(200, json=page([third])),
    )

    async with fake.client() as client:
        keys = [task.key async for task in client.tasks.iter_query("ws", limit=2)]

    assert keys == ["ENG-1", "ENG-2", "ENG-3"]
    assert json.loads(fake.requests[1].content)["cursor"] == "c1"


async def test_update_sends_explicit_null() -> None:
    fake = Fake(httpx.Response(200, json=TASK))

    async with fake.client() as client:
        await client.tasks.update("eng-1", assignee_id=None, priority=1)

    (request,) = fake.requests
    assert (request.method, request.url.path) == ("PATCH", "/api/v1/tasks/eng-1")
    assert json.loads(request.content) == {"assignee_id": None, "priority": 1}


async def test_delete_returns_none_on_204() -> None:
    fake = Fake(httpx.Response(204))

    async with fake.client() as client:
        assert await client.tasks.delete("ENG-1") is None

    assert fake.requests[0].method == "DELETE"


async def test_relation_and_move_bodies() -> None:
    relation = {
        "id": TASK["id"],
        "type": "blocks",
        "task": {"id": TASK["id"], "key": "ENG-2", "title": "x"},
    }
    fake = Fake(httpx.Response(201, json=relation), httpx.Response(200, json=TASK))

    async with fake.client() as client:
        created = await client.tasks.add_relation("ENG-1", kind="blocks", target="ENG-2")
        await client.tasks.move("ENG-1", position="top")

    assert created.task.key == "ENG-2"
    assert json.loads(fake.requests[0].content) == {"type": "blocks", "target_id": "ENG-2"}
    assert json.loads(fake.requests[1].content) == {"position": "top"}
