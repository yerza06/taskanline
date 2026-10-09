"""Критерий готовности этапа 3.

Через API создаётся задача ENG-1, ей назначается исполнитель, она перетаскивается
между статусами, получает подзадачу, связь `blocks` и комментарий с упоминанием; в
`GET /tasks/{id}/activities` видна полная история всех этих действий, а упомянутый
получает уведомление. Попытка создать циклическую связь возвращает `400 relation_cycle`.
"""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import API, create_team, create_workspace, grant, team_states, user_id_of


async def test_stage_three_scenario(
    sign_up: Callable[..., Awaitable[AsyncClient]], db_session: AsyncSession
) -> None:
    lead = await sign_up("lead@example.com", "Лид")
    workspace = await create_workspace(lead)
    team = await create_team(lead, workspace["id"])
    states = await team_states(lead, team["id"])
    dev = await sign_up("dev@example.com", "Разработчик")
    dev_uuid = await user_id_of(db_session, "dev@example.com")
    dev_id = str(dev_uuid)
    await grant(db_session, user_id=dev_uuid, workspace_id=workspace["id"], workspace_role="member")

    created = await lead.post(
        f"{API}/tasks", json={"title": "Починить редирект после логина", "team_id": team["id"]}
    )
    assert created.status_code == 201, created.text
    assert created.json()["key"] == "ENG-1"

    assigned = await lead.patch(f"{API}/tasks/ENG-1", json={"assignee_id": dev_id})
    assert assigned.status_code == 200, assigned.text

    for state in ("In Progress", "Done"):
        moved = await lead.post(
            f"{API}/tasks/ENG-1/move", json={"state_id": states[state]["id"], "position": "top"}
        )
        assert moved.status_code == 200, moved.text
    assert moved.json()["completed_at"] is not None

    subtask = await lead.post(
        f"{API}/tasks",
        json={"title": "Тест на редирект", "team_id": team["id"], "parent_id": "ENG-1"},
    )
    assert subtask.json()["key"] == "ENG-2"

    blocker = await lead.post(f"{API}/tasks", json={"title": "Обновить SDK", "team_id": team["id"]})
    linked = await lead.post(
        f"{API}/tasks/ENG-1/relations", json={"type": "blocks", "target_id": blocker.json()["key"]}
    )
    assert linked.status_code == 201, linked.text

    commented = await lead.post(
        f"{API}/tasks/ENG-1/comments", json={"body": "@dev@example.com посмотри, пожалуйста"}
    )
    assert commented.status_code == 201, commented.text

    history = (await lead.get(f"{API}/tasks/ENG-1/activities")).json()["items"]
    assert [item["type"] for item in reversed(history)] == [
        "task_created",
        "assignee_changed",
        "state_changed",
        "state_changed",
        "relation_added",
        "commented",
    ]

    inbox = (await dev.get(f"{API}/me/notifications")).json()["items"]
    assert {(item["type"], item["task_id"]) for item in inbox} == {
        ("assigned", created.json()["id"]),
        ("mentioned", created.json()["id"]),
    }

    cycle = await lead.post(
        f"{API}/tasks/{blocker.json()['key']}/relations",
        json={"type": "blocks", "target_id": "ENG-1"},
    )
    assert cycle.status_code == 400
    assert cycle.json()["error"]["code"] == "relation_cycle"
