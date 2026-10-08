"""Поддельное API для тестов SDK: записывает запросы и отвечает по сценарию."""

from collections.abc import Callable
from typing import Any

import httpx

from taskanline_sdk import TasKanLineClient

Handler = Callable[[httpx.Request], httpx.Response]

TASK: dict[str, Any] = {
    "id": "019a5c1e-0000-7000-8000-000000000001",
    "key": "ENG-1",
    "workspace_id": "019a5c1e-0000-7000-8000-0000000000aa",
    "team_id": "019a5c1e-0000-7000-8000-0000000000bb",
    "project_id": None,
    "number": 1,
    "title": "Починить логин",
    "description": None,
    "state_id": "019a5c1e-0000-7000-8000-0000000000cc",
    "assignee_id": None,
    "creator_id": "019a5c1e-0000-7000-8000-0000000000dd",
    "priority": 2,
    "due_date": None,
    "parent_id": None,
    "label_ids": [],
    "sort_order": "a0",
    "started_at": None,
    "completed_at": None,
    "created_at": "2026-10-08T10:00:00Z",
    "updated_at": "2026-10-08T10:00:00Z",
    "deleted_at": None,
}


def error(status: int, code: str, message: str = "", **headers: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"error": {"code": code, "message": message, "details": {}}},
        headers=headers,
    )


class Fake:
    """Отвечает ответами из очереди по порядку; все запросы — в `requests`."""

    def __init__(self, *responses: httpx.Response | Handler) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return response(request) if callable(response) else response

    async def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def client(self, **options: Any) -> TasKanLineClient:
        return TasKanLineClient(
            "http://tkl.test",
            "tkl_secret",
            transport=httpx.MockTransport(self._handle),
            sleep=self._sleep,
            **options,
        )
