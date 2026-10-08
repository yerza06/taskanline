"""Ресурсы, промпты и изложение фильтров views словами."""

import httpx
from mcp.types import TextContent, TextResourceContents

from cli_tests.fake_api import AT, BUG, DEV, TASK_ID, TEAM, WS, FakeApi
from mcp_tests.conftest import Connect

VIEW = {
    "id": "019a5c1e-0000-7000-8000-0000000000a1",
    "workspace_id": WS,
    "scope": "team",
    "owner_id": None,
    "team_id": TEAM,
    "name": "Баги",
    "description": "Открытые баги",
    "icon": None,
    "color": None,
    "filters": {
        "assignee_id": {"op": "in", "value": ["@me", DEV]},
        "label_id": {"op": "in", "value": [BUG]},
        "state_type": {"op": "nin", "value": ["completed"]},
        "priority": {"op": "lte", "value": 2},
        "due_date": {"op": "is_null"},
    },
    "group_by": "priority",
    "sort_by": "manual",
    "sort_direction": "asc",
    "layout": "board",
    "position": 0,
    "created_by": DEV,
    "created_at": AT,
    "updated_at": AT,
    "can_edit": True,
}


async def test_views_are_described_in_words(connect: Connect, api: FakeApi) -> None:
    api.routes[("GET", "/views")] = httpx.Response(200, json={"items": [VIEW]})
    api.routes[("GET", f"/teams/{TEAM}/projects")] = httpx.Response(200, json={"items": []})

    async with connect() as client:
        result = await client.call_tool("list_views", {})

    assert result.structured_content is not None
    (view,) = result.structured_content["views"]
    assert view["filters"] == (
        "исполнитель: я, dev@example.com; метка: bug; тип статуса не: completed; "
        "приоритет ≤: high; срок пусто"
    )


async def test_task_resource_is_markdown(connect: Connect, api: FakeApi) -> None:
    api.routes[("GET", f"/tasks/{TASK_ID}/comments")] = httpx.Response(
        200, json={"items": [], "next_cursor": None, "has_more": False}
    )

    async with connect() as client:
        result = await client.read_resource("taskanline://task/ENG-1")

    (content,) = result.contents
    assert isinstance(content, TextResourceContents)
    assert content.text.startswith("# ENG-1: Починить логин")
    assert "- Статус: Todo (unstarted)" in content.text


async def test_prompts_follow_read_only(connect: Connect) -> None:
    async with connect() as writable:
        full = await writable.get_prompt("breakdown_task", {"key": "ENG-1"})
    async with connect(read_only=True) as reader:
        limited = await reader.get_prompt("breakdown_task", {"key": "ENG-1"})

    (message,) = full.messages
    (limited_message,) = limited.messages
    assert isinstance(message.content, TextContent)
    assert isinstance(limited_message.content, TextContent)
    assert "create_task" in message.content.text
    assert "только для чтения" in limited_message.content.text
