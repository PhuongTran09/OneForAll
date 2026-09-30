import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_user(client: AsyncClient):
    # 1. Create User
    payload = {
        "email": "test@example.com",
        "username": "testuser",
        "full_name": "Test User",
        "password": "strongpassword123",
    }
    response = await client.post("/api/v1/users", json=payload)
    assert response.status_code == 201
    created_user = response.json()
    assert created_user["email"] == payload["email"]
    assert created_user["username"] == payload["username"]
    assert "id" in created_user

    user_id = created_user["id"]

    # 2. Get User by ID
    get_response = await client.get(f"/api/v1/users/{user_id}")
    assert get_response.status_code == 200
    user_data = get_response.json()
    assert user_data["id"] == user_id
    assert user_data["email"] == payload["email"]

    # 3. List Users
    list_response = await client.get("/api/v1/users")
    assert list_response.status_code == 200
    users_list = list_response.json()
    assert len(users_list) >= 1
