"""Каталог: имена, схемы и подсказки инструментов; `--read-only` убирает запись."""

from mcp_tests.conftest import Connect

READ = {
    "list_workspaces",
    "list_teams",
    "list_projects",
    "search_tasks",
    "get_task",
    "list_views",
    "run_view",
}
WRITE = {
    "create_task",
    "update_task",
    "assign_task",
    "update_task_state",
    "comment_task",
    "link_tasks",
}

# Снимок контракта: изменение параметров инструмента обязано ломать этот тест.
SCHEMAS = {
    "list_workspaces": ([], []),
    "list_teams": (["workspace"], []),
    "list_projects": (["status", "team"], []),
    "search_tasks": (
        ["assignee", "cursor", "due_before", "label", "limit", "priority", "project", "query",
         "state_type", "team"],
        [],
    ),
    "get_task": (["include", "key"], ["key"]),
    "list_views": ([], []),
    "run_view": (["limit", "view"], ["view"]),
    "create_task": (
        ["assignee", "description", "due_date", "labels", "parent", "priority", "project",
         "state", "team", "title"],
        ["title"],
    ),
    "update_task": (
        ["assignee", "clear", "description", "due_date", "key", "parent", "priority", "project",
         "state", "title"],
        ["key"],
    ),
    "assign_task": (["assignee", "key"], ["assignee", "key"]),
    "update_task_state": (["key", "state"], ["key", "state"]),
    "comment_task": (["body", "key"], ["body", "key"]),
    "link_tasks": (["source", "target", "type"], ["source", "target", "type"]),
}  # fmt: skip


async def test_full_catalog_and_schemas(connect: Connect) -> None:
    async with connect() as client:
        tools = (await client.list_tools()).tools

    assert {tool.name for tool in tools} == READ | WRITE
    for tool in tools:
        properties = sorted(tool.input_schema.get("properties", {}))
        required = sorted(tool.input_schema.get("required", []))
        assert (properties, required) == SCHEMAS[tool.name], tool.name
        assert tool.description and len(tool.description) > 40, tool.name
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is (tool.name in READ), tool.name


async def test_read_only_hides_write_tools(connect: Connect) -> None:
    async with connect(read_only=True) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        refused = await client.call_tool("create_task", {"title": "x"})

    assert names == READ
    assert refused.is_error


async def test_limit_schema_is_capped(connect: Connect) -> None:
    async with connect() as client:
        result = await client.call_tool("search_tasks", {"limit": 500})

    assert result.is_error


async def test_resources_and_prompts_are_listed(connect: Connect) -> None:
    async with connect() as client:
        templates = (await client.list_resource_templates()).resource_templates
        prompts = (await client.list_prompts()).prompts

    assert {t.uri_template for t in templates} == {
        "taskanline://workspace/{slug}",
        "taskanline://team/{key}",
        "taskanline://project/{project_id}",
        "taskanline://task/{key}",
    }
    assert {p.name for p in prompts} == {
        "breakdown_task",
        "project_status",
        "whats_next",
        "standup",
    }
