import io

import pytest
from httpx import AsyncClient
from PIL import Image

from app.repositories.job_repository import JobRepository
from tests.conftest import create_test_supabase_token


def _auth_headers() -> dict[str, str]:
    token = create_test_supabase_token(
        email="media-test@example.com",
        username="mediauser",
        full_name="Media User",
    )
    return {"Authorization": f"Bearer {token}"}


def _create_sample_png() -> bytes:
    img = Image.new("RGB", (32, 32), color="purple")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_image_process_multipart_with_uploaded_file(client: AsyncClient):
    """Test image/process with direct file upload via multipart/form-data."""
    headers = _auth_headers()
    png_bytes = _create_sample_png()

    response = await client.post(
        "/api/v1/image/process",
        headers=headers,
        data={
            "operation": "resize",
            "options": '{"width": 64, "height": 64}',
        },
        files={"file": ("photo.png", png_bytes, "image/png")},
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert response.json()["status"] == "queued"

    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    assert job.type == "image_process"
    assert job.input_key.startswith(f"uploads/{job_id}/original.")
    assert job.job_metadata["operation"] == "resize"
    assert job.job_metadata["options"] == {"width": 64, "height": 64}


@pytest.mark.asyncio
async def test_image_process_multipart_with_input_key(client: AsyncClient):
    """Test image/process with form-data providing input_key."""
    headers = _auth_headers()

    response = await client.post(
        "/api/v1/image/process",
        headers=headers,
        data={
            "input_key": "uploads/existing.png",
            "operation": "remove_background",
        },
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    assert job.input_key == "uploads/existing.png"
    assert job.job_metadata["operation"] == "remove_background"


@pytest.mark.asyncio
async def test_image_process_multipart_missing_input_raises_400(client: AsyncClient):
    """Test image/process without file or input_key returns 400."""
    headers = _auth_headers()

    response = await client.post(
        "/api/v1/image/process",
        headers=headers,
        data={"operation": "compress"},
    )

    assert response.status_code == 400
    assert "Vui lòng tải lên file" in response.json()["detail"]


@pytest.mark.asyncio
async def test_video_jobs_multipart_with_uploaded_file(client: AsyncClient):
    """Test video/jobs with direct file upload via multipart/form-data."""
    headers = _auth_headers()
    fake_video_bytes = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41"

    response = await client.post(
        "/api/v1/video/jobs",
        headers=headers,
        data={
            "operation": "transcode",
            "params": '{"vcodec": "libx264", "crf": "28"}',
        },
        files={"file": ("clip.mp4", fake_video_bytes, "video/mp4")},
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert response.json()["status"] == "queued"

    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    assert job.type == "video"
    assert job.input_key.startswith(f"uploads/{job_id}/original.")
    assert job.job_metadata["operation"] == "transcode"
    assert job.job_metadata["options"] == {"vcodec": "libx264", "crf": "28"}


@pytest.mark.asyncio
async def test_video_jobs_multipart_with_url(client: AsyncClient):
    """Test video/jobs with form-data providing url."""
    headers = _auth_headers()

    response = await client.post(
        "/api/v1/video/jobs",
        headers=headers,
        data={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "operation": "url_download",
            "params": '{"format": "mp3"}',
        },
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    assert job.job_metadata["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert job.job_metadata["operation"] == "url_download"
    assert job.job_metadata["options"] == {"format": "mp3"}


@pytest.mark.asyncio
async def test_video_jobs_multipart_with_tiktok_url_mp3(client: AsyncClient):
    """Test video/jobs with TikTok URL converted to MP3."""
    headers = _auth_headers()

    response = await client.post(
        "/api/v1/video/jobs",
        headers=headers,
        data={
            "url": "https://www.tiktok.com/@scout2015/video/6718335390845095173",
            "operation": "url_download",
            "params": '{"format": "mp3"}',
        },
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    assert job.job_metadata["url"] == "https://www.tiktok.com/@scout2015/video/6718335390845095173"
    assert job.job_metadata["operation"] == "url_download"
    assert job.job_metadata["options"] == {"format": "mp3"}


@pytest.mark.asyncio
async def test_video_jobs_multipart_with_tiktok_url_mp4(client: AsyncClient):
    """Test video/jobs with TikTok URL downloaded to MP4."""
    headers = _auth_headers()

    response = await client.post(
        "/api/v1/video/jobs",
        headers=headers,
        data={
            "url": "https://www.tiktok.com/@scout2015/video/6718335390845095173",
            "operation": "url_download",
            "params": '{"format": "mp4"}',
        },
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    assert job.job_metadata["url"] == "https://www.tiktok.com/@scout2015/video/6718335390845095173"
    assert job.job_metadata["operation"] == "url_download"
    assert job.job_metadata["options"] == {"format": "mp4"}


@pytest.mark.asyncio
async def test_video_jobs_multipart_missing_input_raises_400(client: AsyncClient):
    """Test video/jobs without file, input_file_key, or url returns 400."""
    headers = _auth_headers()

    response = await client.post(
        "/api/v1/video/jobs",
        headers=headers,
        data={"operation": "transcode"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_media_process_primary_route(client: AsyncClient):
    """Verify primary route /api/v1/media/process creates jobs successfully."""
    headers = _auth_headers()
    response = await client.post(
        "/api/v1/media/process",
        headers=headers,
        data={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "operation": "url_download",
            "params": '{"format": "mp3"}',
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["job_id"]
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_video_process_alias_route(client: AsyncClient):
    """Verify alias route /api/v1/video/process creates jobs successfully."""
    headers = _auth_headers()
    response = await client.post(
        "/api/v1/video/process",
        headers=headers,
        data={
            "url": "https://www.tiktok.com/@scout2015/video/6718335390845095173",
            "operation": "url_download",
            "params": '{"format": "mp4"}',
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["job_id"]
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_media_process_anonymous_without_auth(client: AsyncClient):
    """Verify /api/v1/media/process can be called without Authorization header."""
    response = await client.post(
        "/api/v1/media/process",
        data={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "operation": "url_download",
            "params": '{"format": "mp3"}',
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    assert job.user_id == "anonymous"

    # Also verify GET /api/v1/jobs/{job_id} works without auth
    status_res = await client.get(f"/api/v1/jobs/{job_id}")
    assert status_res.status_code == 200
    assert status_res.json()["id"] == job_id


@pytest.mark.asyncio
async def test_image_process_anonymous_without_auth(client: AsyncClient):
    """Verify /api/v1/image/process can be called without Authorization header."""
    png_bytes = _create_sample_png()
    response = await client.post(
        "/api/v1/image/process",
        data={
            "operation": "compress",
            "options": '{"quality": 80}',
        },
        files={"file": ("photo.png", png_bytes, "image/png")},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    assert job.user_id == "anonymous"

    # Also verify GET /api/v1/jobs/{job_id} works without auth
    status_res = await client.get(f"/api/v1/jobs/{job_id}")
    assert status_res.status_code == 200
    assert status_res.json()["id"] == job_id



