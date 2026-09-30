import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_v1(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app_name" in data
    assert "device" in data
    assert "model_loaded" in data


@pytest.mark.asyncio
async def test_health_check_root(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
