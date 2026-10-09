from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_supabase_token


@pytest.mark.asyncio
async def test_get_and_update_my_profile(client: AsyncClient):
    uid = str(uuid4())
    token = create_test_supabase_token(
        user_id=uid,
        email="me@example.com",
        username="myuser",
        full_name="My User",
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Get profile (/users/me)
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == uid
    assert data["email"] == "me@example.com"
    assert data["username"] == "myuser"
    assert data["full_name"] == "My User"
    assert data["is_active"] is True
    assert data["is_superuser"] is False

    # 2. Update profile (/users/me)
    update_res = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"full_name": "Updated Full Name"},
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["full_name"] == "Updated Full Name"


@pytest.mark.asyncio
async def test_superuser_required_for_listing_and_admin_routes(client: AsyncClient):
    # Regular user token
    regular_token = create_test_supabase_token(is_superuser=False)
    regular_headers = {"Authorization": f"Bearer {regular_token}"}

    # Regular user cannot list all users
    list_res = await client.get("/api/v1/users", headers=regular_headers)
    assert list_res.status_code == 403
    assert "Superuser access required" in list_res.json()["detail"]

    # Superuser token
    admin_token = create_test_supabase_token(is_superuser=True)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Superuser can create user profile
    create_res = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "created@example.com",
            "username": "createduser",
            "full_name": "Created User",
        },
    )
    assert create_res.status_code == 201
    created_id = create_res.json()["id"]

    # Superuser can list all users
    admin_list = await client.get("/api/v1/users", headers=admin_headers)
    assert admin_list.status_code == 200
    assert len(admin_list.json()) >= 1

    # Superuser can delete user
    del_res = await client.delete(f"/api/v1/users/{created_id}", headers=admin_headers)
    assert del_res.status_code == 204
