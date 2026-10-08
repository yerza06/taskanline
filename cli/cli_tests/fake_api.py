"""Поддельное API для тестов CLI: маленький мир — workspace acme, команда ENG.

Маршруты — словарь `(метод, путь) → ответ`; тест может подменить любой. Все запросы
записываются, чтобы проверить, что ушло в API (или что не ушло ничего).
"""

import json
import re
from collections.abc import Callable
from typing import Any

import httpx

WS = "019a5c1e-0000-7000-8000-0000000000aa"
TEAM = "019a5c1e-0000-7000-8000-0000000000bb"
TODO = "019a5c1e-0000-7000-8000-0000000000c1"
PROGRESS = "019a5c1e-0000-7000-8000-0000000000c2"
DONE = "019a5c1e-0000-7000-8000-0000000000c3"
CANCELED = "019a5c1e-0000-7000-8000-0000000000c4"
ME = "019a5c1e-0000-7000-8000-0000000000d1"
DEV = "019a5c1e-0000-7000-8000-0000000000d2"
BUG = "019a5c1e-0000-7000-8000-0000000000e1"
TASK_ID = "019a5c1e-0000-7000-8000-000000000001"
AT = "2026-10-08T10:00:00Z"


def state(state_id: str, name: str, kind: str, position: int) -> dict[str, Any]:
    return {
        "id": state_id,
        "workspace_id": WS,
        "team_id": TEAM,
        "name": name,
        "type": kind,
        "color": "#000000",
        "position": position,
        "is_default": name == "Todo",
        "created_at": AT,
    }


STATES = [
    state(TODO, "Todo", "unstarted", 1),
    state(PROGRESS, "In Progress", "started", 2),
    state(DONE, "Done", "completed", 3),
    state(CANCELED, "Canceled", "canceled", 4),
]


def task(**changes: Any) -> dict[str, Any]:
    base = {
        "id": TASK_ID,
        "key": "ENG-1",
        "workspace_id": WS,
        "team_id": TEAM,
        "project_id": None,
        "number": 1,
        "title": "Починить логин",
        "description": "Редирект теряет query",
        "state_id": TODO,
        "assignee_id": ME,
        "creator_id": DEV,
        "priority": 2,
        "due_date": "2026-10-20",
        "parent_id": None,
        "label_ids": [BUG],
        "sort_order": "a0",
        "started_at": None,
        "completed_at": None,
        "created_at": AT,
        "updated_at": AT,
        "deleted_at": None,
        "state": {"id": TODO, "name": "Todo", "type": "unstarted", "color": "#000000"},
        "assignee": {
            "id": ME,
            "email": "agent@example.com",
            "full_name": "Агент",
            "avatar_url": None,
        },
        "creator": {"id": DEV, "email": "dev@example.com", "full_name": "Dev", "avatar_url": None},
        "labels": [{"id": BUG, "name": "bug", "color": "#ff0000"}],
        "project": None,
        "parent": None,
        "relations": [],
    }
    return {**base, **changes}


def error(status: int, code: str, message: str = "", **headers: str) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": code, "message": message, "details": {}}}, headers=headers
    )


Route = Callable[[httpx.Request], httpx.Response] | httpx.Response


class FakeApi:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        member = {"avatar_url": None, "joined_at": AT}
        self.routes: dict[tuple[str, str], Route] = {
            ("GET", "/me"): httpx.Response(
                200,
                json={
                    "id": ME,
                    "email": "agent@example.com",
                    "full_name": "Агент",
                    "avatar_url": None,
                    "role": "user",
                    "created_at": AT,
                    "auth_method": "token",
                    "scopes": ["read", "write"],
                    "memberships": {
                        "workspaces": [{"workspace_id": WS, "role": "member"}],
                        "teams": [],
                        "projects": [],
                    },
                },
            ),
            ("GET", "/workspaces"): httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": WS,
                            "name": "Acme",
                            "slug": "acme",
                            "avatar_url": None,
                            "created_by": DEV,
                            "created_at": AT,
                            "updated_at": AT,
                        }
                    ]
                },
            ),
            ("GET", f"/workspaces/{WS}/teams"): httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": TEAM,
                            "workspace_id": WS,
                            "key": "ENG",
                            "name": "Инженерия",
                            "description": None,
                            "is_private": False,
                            "created_at": AT,
                            "updated_at": AT,
                        }
                    ]
                },
            ),
            ("GET", f"/workspaces/{WS}/members"): httpx.Response(
                200,
                json={
                    "items": [
                        {
                            **member,
                            "user_id": ME,
                            "email": "agent@example.com",
                            "full_name": "Агент",
                            "role": "member",
                        },
                        {
                            **member,
                            "user_id": DEV,
                            "email": "dev@example.com",
                            "full_name": "Dev",
                            "role": "admin",
                        },
                    ]
                },
            ),
            ("GET", f"/teams/{TEAM}/states"): httpx.Response(200, json={"items": STATES}),
            ("GET", "/labels"): httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": BUG,
                            "workspace_id": WS,
                            "team_id": None,
                            "name": "bug",
                            "color": "#ff0000",
                            "created_at": AT,
                        }
                    ]
                },
            ),
            ("POST", "/views/query"): self._query,
            ("GET", "/tasks/ENG-1"): httpx.Response(200, json=task()),
            ("GET", f"/tasks/{TASK_ID}"): httpx.Response(200, json=task()),
            ("GET", "/tasks/ENG-999"): error(404, "task_not_found", "Задача не найдена"),
            ("PATCH", f"/tasks/{TASK_ID}"): self._patch,
            ("POST", f"/tasks/{TASK_ID}/comments"): self._comment,
        }

    def _query(self, request: httpx.Request) -> httpx.Response:
        group = {"key": None, "count": 1, "items": [task()], "next_cursor": None, "has_more": False}
        return httpx.Response(200, json={"group_by": None, "groups": [group]})

    def _patch(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=task(**json.loads(request.content)))

    def _comment(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)["body"]
        return httpx.Response(
            201,
            json={
                "id": "019a5c1e-0000-7000-8000-0000000000f1",
                "task_id": TASK_ID,
                "author_id": ME,
                "author_token_id": "019a5c1e-0000-7000-8000-0000000000f2",
                "parent_id": None,
                "body": body,
                "mention_ids": [],
                "created_at": AT,
                "updated_at": AT,
            },
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = re.sub(r"^/api/v1", "", request.url.path)
        route = self.routes.get((request.method, path))
        if route is None:
            return error(404, "route_not_faked", f"{request.method} {path}")
        return route(request) if callable(route) else route

    def sent(self, method: str, path: str) -> list[httpx.Request]:
        return [
            request
            for request in self.requests
            if request.method == method and request.url.path == f"/api/v1{path}"
        ]
