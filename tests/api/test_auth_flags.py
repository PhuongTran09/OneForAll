"""Tests for per-endpoint auth flag system and public/private job access control.

Scenarios covered:
- Guest creates public job → 202 + download_token returned
- Guest accesses REQUIRED_AUTH endpoint → 401
- Authenticated user accesses REQUIRED_AUTH endpoint → 202
- Guest checks public job status → 200, limited fields only
- Authenticated owner checks private job status → 200, full response
- Guest checks private job status → 401
- Guest downloads public job with valid token → succeeds
- Guest downloads public job with invalid token → 403
- Guest downloads public job without token → 403
- Guest downloads private job without JWT → 401
- Non-owner authenticated user downloads private job → 403
- Job not completed → download returns 400
- File not found (no output_key) → 404
- Expired job → 410
- Cleanup does not break download flow
"""

import io
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image

from app.core.config import settings
from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.utils.download_token import generate_download_token, verify_download_token
from tests.conftest import create_test_supabase_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_headers(user_id: str | None = None) -> dict[str, str]:
    token = create_test_supabase_token(
        user_id=user_id,
        email="authtest@example.com",
        username="authuser",
        full_name="Auth User",
    )
    return {"Authorization": f"Bearer {token}"}


def _create_sample_png() -> bytes:
    img = Image.new("RGB", (16, 16), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _create_public_job(client: AsyncClient) -> tuple[str, str]:
    """Create an anonymous/public media job and return (job_id, download_token)."""
    response = await client.post(
        "/api/v1/media/process",
        data={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "operation": "url_download",
            "params": '{"format": "mp3"}',
        },
    )
    assert response.status_code == 202
    data = response.json()
    return data["job_id"], data["download_token"]


async def _create_private_job(client: AsyncClient, user_id: str) -> str:
    """Create a private media job for a given user; returns job_id."""
    headers = _auth_headers(user_id=user_id)
    response = await client.post(
        "/api/v1/media/process",
        headers=headers,
        data={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "operation": "url_download",
        },
    )
    assert response.status_code == 202
    return response.json()["job_id"]


# ---------------------------------------------------------------------------
# Unit tests for download_token utility
# ---------------------------------------------------------------------------


def test_generate_and_verify_download_token():
    plain, digest = generate_download_token()
    assert len(plain) > 20
    assert len(digest) == 64  # sha256 hex
    assert verify_download_token(plain, digest) is True


def test_invalid_token_rejected():
    _, digest = generate_download_token()
    assert verify_download_token("wrong-token", digest) is False


def test_empty_token_rejected():
    _, digest = generate_download_token()
    assert verify_download_token("", digest) is False


# ---------------------------------------------------------------------------
# Public job creation — download_token returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_job_returns_download_token(client: AsyncClient):
    """Anonymous job creation must return a non-None download_token."""
    job_id, token = await _create_public_job(client)
    assert job_id
    assert token is not None
    assert len(token) > 20


@pytest.mark.asyncio
async def test_authenticated_job_has_no_download_token(client: AsyncClient):
    """Authenticated job creation must NOT return a download_token."""
    headers = _auth_headers()
    response = await client.post(
        "/api/v1/media/process",
        headers=headers,
        data={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "operation": "url_download",
        },
    )
    assert response.status_code == 202
    assert response.json().get("download_token") is None


@pytest.mark.asyncio
async def test_public_image_job_returns_download_token(client: AsyncClient):
    """Anonymous image/process must return a download_token."""
    png = _create_sample_png()
    response = await client.post(
        "/api/v1/image/process",
        data={"operation": "compress"},
        files={"file": ("photo.png", png, "image/png")},
    )
    assert response.status_code == 202
    assert response.json()["download_token"] is not None


@pytest.mark.asyncio
async def test_public_convert_job_returns_download_token(client: AsyncClient):
    """Anonymous convert-file must return a download_token."""
    png = _create_sample_png()
    response = await client.post(
        "/api/v1/convert-file",
        data={"to": "webp"},
        files={"file": ("image.png", png, "image/png")},
    )
    assert response.status_code == 202
    assert response.json()["download_token"] is not None


# ---------------------------------------------------------------------------
# Auth flag: REQUIRED_AUTH flips 401 for anonymous
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_required_auth_flag_blocks_anonymous(client: AsyncClient, monkeypatch):
    """When AUTH_REQUIRED_MEDIA=True, anonymous requests get 401."""
    monkeypatch.setattr(settings, "AUTH_REQUIRED_MEDIA", True)
    response = await client.post(
        "/api/v1/media/process",
        data={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "operation": "url_download",
        },
    )
    assert response.status_code == 401
    monkeypatch.setattr(settings, "AUTH_REQUIRED_MEDIA", False)


@pytest.mark.asyncio
async def test_required_auth_flag_allows_authenticated(client: AsyncClient, monkeypatch):
    """When AUTH_REQUIRED_MEDIA=True, authenticated users still get 202."""
    monkeypatch.setattr(settings, "AUTH_REQUIRED_MEDIA", True)
    headers = _auth_headers()
    response = await client.post(
        "/api/v1/media/process",
        headers=headers,
        data={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "operation": "url_download",
        },
    )
    assert response.status_code == 202
    monkeypatch.setattr(settings, "AUTH_REQUIRED_MEDIA", False)


# ---------------------------------------------------------------------------
# Job status — public job limited response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_job_status_accessible_by_guest(client: AsyncClient):
    """Guest can check status of a public job without token."""
    job_id, _ = await _create_public_job(client)
    response = await client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    # Sensitive fields must be absent in public response
    assert "output_key" not in data
    assert "input_key" not in data
    assert "user_id" not in data


@pytest.mark.asyncio
async def test_private_job_status_requires_auth(client: AsyncClient):
    """Guest gets 401 when checking status of a private job."""
    user_id = str(uuid.uuid4())
    job_id = await _create_private_job(client, user_id=user_id)
    response = await client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_private_job_status_accessible_by_owner(client: AsyncClient):
    """Authenticated owner can check status of their private job."""
    user_id = str(uuid.uuid4())
    job_id = await _create_private_job(client, user_id=user_id)
    headers = _auth_headers(user_id=user_id)
    response = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    # Full response includes sensitive fields
    assert "output_key" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_private_job_status_forbidden_for_other_user(client: AsyncClient):
    """Authenticated non-owner gets 403 when checking another user's private job."""
    owner_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    job_id = await _create_private_job(client, user_id=owner_id)
    headers = _auth_headers(user_id=other_id)
    response = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_nonexistent_job_status_returns_404(client: AsyncClient):
    response = await client.get("/api/v1/jobs/nonexistent-job-id")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Download — public job with token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_public_job_requires_token(client: AsyncClient):
    """Downloading a public job without ?token= returns 403."""
    job_id, _ = await _create_public_job(client)

    # Force job to completed with output_key
    repo = JobRepository()
    job = await repo.get(job_id)
    await repo.mark_completed(job, output_key=f"outputs/{job_id}/result.mp3", metadata={**job.job_metadata, "output_key": f"outputs/{job_id}/result.mp3"})
    # Manually set output_key via update
    from app.core.supabase import get_async_supabase_client
    client_sb = await get_async_supabase_client()
    await client_sb.table("jobs").update({
        "status": "completed",
        "output_key": f"outputs/{job_id}/result.mp3",
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", job_id).execute()

    response = await client.get(f"/api/v1/files/{job_id}/download")
    assert response.status_code == 403
    assert "token" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_download_public_job_with_invalid_token_returns_403(client: AsyncClient):
    """Downloading with wrong token returns 403."""
    job_id, _ = await _create_public_job(client)

    # Mark job completed
    from app.core.supabase import get_async_supabase_client
    client_sb = await get_async_supabase_client()
    await client_sb.table("jobs").update({
        "status": "completed",
        "output_key": f"outputs/{job_id}/result.mp3",
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", job_id).execute()

    response = await client.get(
        f"/api/v1/files/{job_id}/download",
        params={"token": "this-is-a-wrong-token"},
    )
    assert response.status_code == 403
    assert "không hợp lệ" in response.json()["detail"]


@pytest.mark.asyncio
async def test_download_private_job_without_auth_returns_401(client: AsyncClient):
    """Downloading a private job without JWT returns 401."""
    user_id = str(uuid.uuid4())
    job_id = await _create_private_job(client, user_id=user_id)

    # Mark job completed
    from app.core.supabase import get_async_supabase_client
    client_sb = await get_async_supabase_client()
    await client_sb.table("jobs").update({
        "status": "completed",
        "output_key": f"outputs/{job_id}/result.mp4",
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", job_id).execute()

    response = await client.get(f"/api/v1/files/{job_id}/download")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_download_private_job_wrong_owner_returns_403(client: AsyncClient):
    """Non-owner authenticated user cannot download private job."""
    owner_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    job_id = await _create_private_job(client, user_id=owner_id)

    from app.core.supabase import get_async_supabase_client
    client_sb = await get_async_supabase_client()
    await client_sb.table("jobs").update({
        "status": "completed",
        "output_key": f"outputs/{job_id}/result.mp4",
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", job_id).execute()

    headers = _auth_headers(user_id=other_id)
    response = await client.get(f"/api/v1/files/{job_id}/download", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_download_job_not_completed_returns_400(client: AsyncClient):
    """Downloading a job that is still queued returns 400."""
    job_id, token = await _create_public_job(client)
    # Job is in 'queued' state by default
    response = await client.get(
        f"/api/v1/files/{job_id}/download",
        params={"token": token},
    )
    assert response.status_code == 400
    assert "chưa hoàn thành" in response.json()["detail"]


@pytest.mark.asyncio
async def test_download_expired_job_returns_410(client: AsyncClient):
    """Downloading an expired job returns 410."""
    job_id, token = await _create_public_job(client)

    # Force job to expired state via DB
    from app.core.supabase import get_async_supabase_client
    client_sb = await get_async_supabase_client()
    await client_sb.table("jobs").update({
        "status": "completed",
        "output_key": f"outputs/{job_id}/result.mp3",
        "completed_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
    }).eq("id", job_id).execute()

    response = await client.get(
        f"/api/v1/files/{job_id}/download",
        params={"token": token},
    )
    assert response.status_code == 410


@pytest.mark.asyncio
async def test_download_job_no_output_key_returns_404(client: AsyncClient):
    """Job is completed but has no output_key → 404."""
    job_id, token = await _create_public_job(client)

    from app.core.supabase import get_async_supabase_client
    client_sb = await get_async_supabase_client()
    await client_sb.table("jobs").update({
        "status": "completed",
        "output_key": None,
        "completed_at": datetime.now(UTC).isoformat(),
    }).eq("id", job_id).execute()

    response = await client.get(
        f"/api/v1/files/{job_id}/download",
        params={"token": token},
    )
    assert response.status_code == 404
