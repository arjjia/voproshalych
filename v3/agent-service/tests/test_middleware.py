import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def test_app():
    from src.main import app
    return app


@pytest.mark.asyncio
async def test_x_user_id_header_passed_through(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"query": "привет"},
            headers={"X-User-Id": "test-user-123", "X-User-Role": "student"},
        )
        assert response.status_code == 200
        assert "X-Request-Id" in response.headers


@pytest.mark.asyncio
async def test_anonymous_default(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"query": "привет"},
        )
        assert response.status_code == 200
        assert "X-Request-Id" in response.headers


@pytest.mark.asyncio
async def test_health_works(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_trace_endpoint_empty(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/trace", params={"request_id": "nonexistent-id"})
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "nonexistent-id"
        assert data["traces"] == []
