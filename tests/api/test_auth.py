from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_supabase_token


@pytest.mark.asyncio
async def test_supabase_auth_success(client: AsyncClient):
    uid = str(uuid4())
    token = create_test_supabase_token(user_id=uid, email="user@supabase.test", username="supabaseuser")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == uid
    assert data["email"] == "user@supabase.test"
    assert data["username"] == "supabaseuser"


@pytest.mark.asyncio
async def test_supabase_auth_missing_token(client: AsyncClient):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]


@pytest.mark.asyncio
async def test_supabase_auth_invalid_token(client: AsyncClient):
    headers = {"Authorization": "Bearer invalid.fake.token"}
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legacy_auth_login_removed(client: AsyncClient):
    # Verifies custom /auth/login route has been removed
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "password"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_superuser_protection(client: AsyncClient):
    normal_token = create_test_supabase_token(is_superuser=False)
    admin_token = create_test_supabase_token(is_superuser=True)

    # Normal user is blocked
    res_normal = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {normal_token}"})
    assert res_normal.status_code == 403

    # Superuser is allowed
    res_admin = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
