import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(async_client: AsyncClient):
    # Test health check endpoint without network calls
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "EvidenceGuard"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_landing_page_renders_ukrainian(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert "EvidenceGuard" in response.text
    assert "Черга перевірки" in response.text
