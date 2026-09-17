from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import ApiError


async def test_unknown_route_returns_unified_error_shape(client: AsyncClient) -> None:
    response = await client.get("/no-such-route")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": {}}
    }


async def test_wrong_method_returns_unified_error_shape(client: AsyncClient) -> None:
    response = await client.post("/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


async def test_validation_error_is_converted_to_unified_shape(app: FastAPI) -> None:
    @app.get("/_test/{number}")
    async def _typed_route(number: int) -> dict[str, int]:
        return {"number": number}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/_test/not-a-number")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["errors"][0]["loc"] == ["path", "number"]


async def test_api_error_is_rendered_with_its_code_and_details(app: FastAPI) -> None:
    @app.get("/_test/domain-error")
    async def _failing_route() -> None:
        raise ApiError(
            status_code=400,
            code="relation_cycle",
            message="Связь создаёт цикл",
            details={"task_key": "ENG-142"},
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/_test/domain-error")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "relation_cycle",
            "message": "Связь создаёт цикл",
            "details": {"task_key": "ENG-142"},
        }
    }


async def test_unhandled_exception_returns_internal_error_without_leaking_details(
    app: FastAPI,
) -> None:
    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("пароль от базы: hunter2")

    # raise_app_exceptions=False: ServerErrorMiddleware отдаёт ответ и пробрасывает
    # исключение дальше — в бою его ловит uvicorn, в тесте пришлось бы ловить нам.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/_test/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text
