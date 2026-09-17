from uuid import UUID

from httpx import AsyncClient


async def test_incoming_request_id_is_echoed_back(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "trace-abc"})

    assert response.headers["X-Request-ID"] == "trace-abc"


async def test_request_id_is_generated_when_header_is_absent(client: AsyncClient) -> None:
    response = await client.get("/health")

    UUID(response.headers["X-Request-ID"])  # выбросит ValueError, если это не UUID
