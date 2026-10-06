import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "image-user@example.com",
            "username": "imageuser",
            "full_name": "Image User",
            "password": "strongpassword123",
        },
    )
    token = create_access_token(str(response.json()["id"]))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_remove_background_is_created_as_image_job(client: AsyncClient):
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/image/process",
        headers=headers,
        json={
            "input_key": "uploads/photo.png",
            "operation": "remove_background",
            "options": {},
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_legacy_remove_bg_route_is_not_registered(client: AsyncClient):
    response = await client.post("/api/v1/remove-bg")
    assert response.status_code == 404
