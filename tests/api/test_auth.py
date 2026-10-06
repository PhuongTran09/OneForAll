import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_login_success(client: AsyncClient):
    # 1. Create a user
    await client.post(
        "/api/v1/users",
        json={
            "email": "authuser@example.com",
            "username": "authuser",
            "full_name": "Auth User",
            "password": "mypassword123",
        },
    )

    # 2. Login via username
    login_response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "authuser",
            "password": "mypassword123",
        },
    )
    assert login_response.status_code == 200
    token_data = login_response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 3. Login via email in username field
    login_email_response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "authuser@example.com",
            "password": "mypassword123",
        },
    )
    assert login_email_response.status_code == 200
    assert "access_token" in login_email_response.json()


@pytest.mark.asyncio
async def test_auth_login_invalid_password(client: AsyncClient):
    await client.post(
        "/api/v1/users",
        json={
            "email": "wrongpass@example.com",
            "username": "wrongpass",
            "full_name": "Wrong Pass",
            "password": "correctpassword",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "wrongpass",
            "password": "badpassword",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Incorrect username or password"
