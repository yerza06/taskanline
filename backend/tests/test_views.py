"""Views: CRUD и права трёх scope.

| scope     | видят                         | меняют                              |
|-----------|-------------------------------|-------------------------------------|
| user      | владелец                      | владелец                            |
| team      | участники команды             | автор, лид команды, admin workspace |
| workspace | все участники, кроме гостей   | автор, admin workspace              |
"""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import API, create_team, create_workspace
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


async def make_view(client: AsyncClient, w: World, scope: str, **fields: Any) -> Any:
    body: dict[str, Any] = {"workspace_id": w.workspace["id"], "scope": scope, "name": scope}
    if scope == "team":
        body["team_id"] = w.team["id"]
    return await client.post(f"{API}/views", json={**body, **fields})


async def visible_names(client: AsyncClient, w: World) -> list[str]:
    response = await client.get(f"{API}/views", params={"workspace_id": w.workspace["id"]})
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


class TestCreate:
    async def test_defaults_and_positions(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()

        first = await make_view(w.owner, w, "user", name="Первый")
        second = await make_view(
            w.owner,
            w,
            "user",
            name="Второй",
            filters={"assignee_id": {"op": "in", "value": ["@me"]}},
            group_by="priority",
            layout="board",
        )

        assert first.status_code == 201, first.text
        body = second.json()
        assert (first.json()["position"], body["position"]) == (0, 1)
        assert (body["sort_by"], body["sort_direction"], body["layout"]) == (
            "manual",
            "asc",
            "board",
        )
        assert body["filters"] == {"assignee_id": {"op": "in", "value": ["@me"]}}
        assert body["owner_id"] is not None and body["can_edit"] is True

    async def test_invalid_definitions_are_422(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()

        for fields in (
            {"filters": {"asignee": {"op": "in", "value": ["@me"]}}},
            {"filters": {"priority": {"op": "contains", "value": "1"}}},
            {"group_by": "mood"},
            {"sort_by": "random"},
            {"team_id": w.team["id"]},
        ):
            response = await make_view(w.owner, w, "user", **fields)
            assert response.status_code == 422, fields
        no_team = await w.owner.post(
            f"{API}/views",
            json={"workspace_id": w.workspace["id"], "scope": "team", "name": "Без команды"},
        )
        assert no_team.status_code == 422

    async def test_who_creates_what(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        guest, _ = await w.person("guest@example.com", workspace_role="guest")
        member, _ = await w.person("member@example.com", workspace_role="member")
        stranger, _ = await w.person("stranger@example.com")

        assert (await make_view(guest, w, "user")).status_code == 201
        assert (await make_view(guest, w, "team")).status_code == 404
        assert (await make_view(member, w, "team")).status_code == 201
        denied = await make_view(member, w, "workspace")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "insufficient_role"
        assert (await make_view(w.owner, w, "workspace")).status_code == 201
        assert (await make_view(stranger, w, "user")).status_code == 404

    async def test_team_of_other_workspace_is_404(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        other = await create_workspace(w.owner, slug="other", name="Other")
        response = await w.owner.post(
            f"{API}/views",
            json={
                "workspace_id": other["id"],
                "scope": "team",
                "team_id": w.team["id"],
                "name": "x",
            },
        )
        assert response.status_code == 404

    async def test_read_token_cannot_create(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        token = (await w.owner.post(f"{API}/me/tokens", json={"name": "reader"})).json()["token"]

        response = await w.owner.post(
            f"{API}/views",
            json={"workspace_id": w.workspace["id"], "scope": "user", "name": "x"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_scope"


class TestVisibility:
    async def test_list_by_scope(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        secret = await create_team(w.owner, w.workspace["id"], key="SEC", is_private=True)
        await make_view(w.owner, w, "user", name="Мой")
        await make_view(w.owner, w, "team", name="Команды")
        await w.owner.post(
            f"{API}/views",
            json={
                "workspace_id": w.workspace["id"],
                "scope": "team",
                "team_id": secret["id"],
                "name": "Тайный",
            },
        )
        await make_view(w.owner, w, "workspace", name="Общий")
        member, _ = await w.person("member@example.com", workspace_role="member")
        guest, _ = await w.person(
            "guest@example.com", workspace_role="guest", team_id=w.team["id"], team_role="member"
        )
        contractor, _ = await w.person(
            "contractor@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="member",
        )

        assert await visible_names(w.owner, w) == ["Мой", "Команды", "Тайный", "Общий"]
        assert await visible_names(member, w) == ["Команды", "Общий"]
        assert await visible_names(guest, w) == ["Команды"]
        assert await visible_names(contractor, w) == []

    async def test_foreign_personal_view_is_404(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        mine = (await make_view(w.owner, w, "user")).json()
        admin, _ = await w.person("admin@example.com", workspace_role="admin")

        for method in ("GET", "PATCH", "DELETE"):
            response = await admin.request(
                method,
                f"{API}/views/{mine['id']}",
                json={"name": "x"} if method == "PATCH" else None,
            )
            assert response.status_code == 404, method
            assert response.json()["error"]["code"] == "view_not_found"
        tasks = await admin.get(f"{API}/views/{mine['id']}/tasks")
        assert tasks.status_code == 404

    async def test_garbage_id_is_404(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()

        for ref in ("nope", "00000000-0000-0000-0000-000000000000"):
            assert (await w.owner.get(f"{API}/views/{ref}")).status_code == 404


class TestEdit:
    async def test_team_view_rights(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        author, _ = await w.person("author@example.com", workspace_role="member")
        peer, _ = await w.person("peer@example.com", workspace_role="member")
        lead, _ = await w.person(
            "lead@example.com", workspace_role="member", team_id=w.team["id"], team_role="lead"
        )
        view = (await make_view(author, w, "team")).json()
        url = f"{API}/views/{view['id']}"

        seen = (await peer.get(url)).json()
        by_peer = await peer.patch(url, json={"name": "Чужой"})
        by_author = await author.patch(url, json={"name": "Автор"})
        by_lead = await lead.patch(url, json={"name": "Лид"})
        by_admin = await w.owner.patch(url, json={"layout": "board"})

        assert seen["can_edit"] is False
        assert by_peer.status_code == 403
        assert by_peer.json()["error"]["code"] == "insufficient_role"
        assert by_author.json()["name"] == "Автор"
        assert by_lead.json()["name"] == "Лид"
        assert by_admin.json()["layout"] == "board"

    async def test_workspace_view_rights(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        view = (await make_view(w.owner, w, "workspace")).json()
        member, _ = await w.person("member@example.com", workspace_role="member")
        admin, _ = await w.person("admin@example.com", workspace_role="admin")
        guest, _ = await w.person("guest@example.com", workspace_role="guest")
        url = f"{API}/views/{view['id']}"

        assert (await guest.get(url)).status_code == 404
        assert (await member.get(url)).json()["can_edit"] is False
        assert (await member.delete(url)).status_code == 403
        assert (await admin.delete(url)).status_code == 204
        assert (await w.owner.get(url)).status_code == 404

    async def test_update_rules(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        view = (await make_view(w.owner, w, "user")).json()
        url = f"{API}/views/{view['id']}"

        filters = {"state_type": {"op": "nin", "value": ["completed"]}}
        changed = await w.owner.patch(url, json={"filters": filters, "group_by": "state"})
        cleared = await w.owner.patch(url, json={"group_by": None})
        scope = await w.owner.patch(url, json={"scope": "workspace"})
        null_name = await w.owner.patch(url, json={"name": None})
        bad_filter = await w.owner.patch(url, json={"filters": {"x": {"op": "eq", "value": 1}}})

        assert changed.json()["filters"] == filters
        assert changed.json()["group_by"] == "state"
        assert cleared.json()["group_by"] is None
        assert scope.status_code == 422
        assert null_name.status_code == 422
        assert bad_filter.status_code == 422

    async def test_team_deletion_takes_its_views(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        view = (await make_view(w.owner, w, "team")).json()

        await w.owner.delete(f"{API}/teams/{w.team['id']}")

        assert (await w.owner.get(f"{API}/views/{view['id']}")).status_code == 404
