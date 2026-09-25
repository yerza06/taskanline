"""Критерий готовности этапа 2: сценарий подрядчика.

A создаёт workspace, команду и два проекта; приглашает B только в первый проект.
B видит первый проект, получает 404 на второй проект и на команду целиком.
"""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from tests.org import (
    API,
    PASSWORD,
    RecordingMailer,
    create_project,
    create_team,
    create_workspace,
    invite_token,
)


async def test_contractor_sees_exactly_one_project(
    sign_up: Callable[..., Awaitable[AsyncClient]],
    new_client: Callable[[], AsyncClient],
    mailer: RecordingMailer,
) -> None:
    alice = await sign_up("alice@example.com", "Алиса")
    workspace = await create_workspace(alice)
    team = await create_team(alice, workspace["id"])
    first = await create_project(alice, team["id"], name="Первый")
    second = await create_project(alice, team["id"], name="Второй")
    invited = await alice.post(
        f"{API}/invitations",
        json={
            "email": "bob@contractor.example",
            "scope_type": "project",
            "scope_id": first["id"],
            "role": "member",
        },
    )
    assert invited.status_code == 201

    bob = new_client()
    accepted = await bob.post(
        f"{API}/invitations/token/{invite_token(mailer)}/accept",
        json={"full_name": "Боб", "password": PASSWORD},
    )
    assert accepted.status_code == 200

    assert (await bob.get(f"{API}/projects/{first['id']}")).status_code == 200
    assert (await bob.get(f"{API}/projects/{second['id']}")).status_code == 404
    assert (await bob.get(f"{API}/teams/{team['id']}")).status_code == 404
    assert (await bob.get(f"{API}/teams/{team['id']}/projects")).status_code == 404
    # Само пространство гостю видно — но не его команды и не участники.
    assert (await bob.get(f"{API}/workspaces/{workspace['id']}")).status_code == 200
    teams = await bob.get(f"{API}/workspaces/{workspace['id']}/teams")
    assert teams.json()["items"] == []
    assert (await bob.get(f"{API}/workspaces/{workspace['id']}/members")).status_code == 403
    projects = (await bob.get(f"{API}/me")).json()["memberships"]["projects"]
    assert [p["project_id"] for p in projects] == [first["id"]]
