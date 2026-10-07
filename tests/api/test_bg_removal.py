import pytest
from httpx import AsyncClient

from tests.conftest import create_test_supabase_token


def _auth_headers() -> dict[str, str]:
    token = create_test_supabase_token(
        email="image-user@example.com",
        username="imageuser",
        full_name="Image User",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_remove_background_is_created_as_image_job(client: AsyncClient):
    headers = _auth_headers()
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
