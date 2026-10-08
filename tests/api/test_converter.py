from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.repositories.job_repository import JobRepository
from tests.conftest import create_test_supabase_token


def _auth_headers() -> dict[str, str]:
    token = create_test_supabase_token(
        email="job-user@example.com",
        username="jobuser",
        full_name="Job User",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_convert_file_job(client: AsyncClient):
    headers = _auth_headers()
    response = await client.post(
        "/api/v1/convert-file",
        headers=headers,
        data={
            "input_key": "uploads/report.txt",
            "from": "txt",
            "to": "pdf",
            "options": '{"title": "OneForAll Report"}',
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["job_id"]
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_create_convert_file_job_with_uploaded_file(client: AsyncClient):
    headers = _auth_headers()
    response = await client.post(
        "/api/v1/convert-file",
        headers=headers,
        data={
            "to": "svg",
        },
        files={
            "file": ("sample.png", b"\x89PNG\r\n\x1a\nfakebytes", "image/png"),
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["job_id"]
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_create_image_job(client: AsyncClient):
    headers = _auth_headers()
    response = await client.post(
        "/api/v1/image/process",
        headers=headers,
        json={
            "input_key": "uploads/image.png",
            "operation": "compress",
            "options": {"quality": 90},
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_get_job_status(client: AsyncClient):
    headers = _auth_headers()
    create_response = await client.post(
        "/api/v1/convert-file",
        headers=headers,
        data={
            "input_key": "uploads/data.xlsx",
            "from": "xlsx",
            "to": "pdf",
        },
    )
    job_id = create_response.json()["job_id"]

    response = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert data["type"] == "convert_file"
    assert data["status"] == "queued"
    assert data["progress"] == 0
    assert data["input_key"] == "uploads/data.xlsx"
    assert data["output_key"] is None
    assert data["error"] is None
    assert data["metadata"] == {
        "from": "xlsx",
        "to": "pdf",
        "operation": "xlsx-to-pdf",
        "options": {},
    }
    assert data["started_at"] is None
    assert data["completed_at"] is None


@pytest.mark.asyncio
async def test_create_presigned_upload_url(client: AsyncClient):
    headers = _auth_headers()
    response = await client.post(
        "/api/v1/files/presigned-upload-url",
        headers=headers,
        json={
            "key": "uploads/report.txt",
            "content_type": "text/plain",
            "expires_in": 900,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["method"] == "PUT"
    assert data["key"] == "uploads/report.txt"


@pytest.mark.asyncio
async def test_download_job_result_file(client: AsyncClient):
    headers = _auth_headers()
    # 1. Create a job
    create_response = await client.post(
        "/api/v1/convert-file",
        headers=headers,
        data={"input_key": "uploads/my.txt", "from": "txt", "to": "pdf"},
    )
    job_id = create_response.json()["job_id"]

    # 2. Before completion -> 400
    down_before = await client.get(f"/api/v1/files/{job_id}/download", headers=headers)
    assert down_before.status_code == 400

    # 3. Simulate completion in database
    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    expires_at = datetime.now(UTC) + timedelta(minutes=20)
    await repo.mark_completed(
        job, output_key=f"outputs/{job_id}/result.pdf", expires_at=expires_at
    )

    # 4. Now download succeeds
    down_after = await client.get(f"/api/v1/files/{job_id}/download", headers=headers)
    assert down_after.status_code == 200
    down_data = down_after.json()
    assert down_data["key"] == f"outputs/{job_id}/result.pdf"
    assert down_data["method"] == "GET"
    assert "url" in down_data


@pytest.mark.asyncio
async def test_anonymous_convert_file_lifecycle(client: AsyncClient):
    # 1. Anonymous create convert-file job (no Authorization header)
    response = await client.post(
        "/api/v1/convert-file",
        data={"to": "svg"},
        files={"file": ("test.png", b"\x89PNG\r\n\x1a\ntestdata", "image/png")},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert response.json()["status"] == "queued"

    # 2. Anonymous check job status (no Authorization header)
    job_res = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    job_info = job_res.json()
    assert job_info["id"] == job_id
    assert job_info["user_id"] == "anonymous"
    assert job_info["status"] == "queued"

    # 3. Simulate Celery worker completing the job
    repo = JobRepository()
    job = await repo.get(job_id)
    assert job is not None
    expires_at = datetime.now(UTC) + timedelta(minutes=20)
    await repo.mark_completed(
        job,
        output_key=f"outputs/{job_id}/result.svg",
        expires_at=expires_at,
    )

    # 4. Anonymous download result (no Authorization header)
    download_res = await client.get(f"/api/v1/files/{job_id}/download")
    assert download_res.status_code == 200
    download_data = download_res.json()
    assert download_data["key"] == f"outputs/{job_id}/result.svg"
    assert "url" in download_data

    # 4.1 Direct binary download without redirect (?direct=true)
    direct_res = await client.get(f"/api/v1/files/{job_id}/download?direct=true")
    assert direct_res.status_code == 200
    assert 'attachment; filename="result.svg"' in direct_res.headers.get("content-disposition", "")
    assert direct_res.content == b"fake-file-content" or len(direct_res.content) > 0

    # 4.2 Khi download thành công, file và job được xóa ngay lập tức
    assert await repo.get(job_id) is None

    # 5. Simulate expiration trên một job không được tải (sau 3 phút)
    exp_job = await repo.create(
        user_id="anonymous",
        type="convert",
        input_key=None,
    )
    past_expires = datetime.now(UTC) - timedelta(minutes=1)
    await repo.mark_completed(
        exp_job,
        output_key=f"outputs/{exp_job.id}/result.svg",
        expires_at=past_expires,
    )

    expired_res = await client.get(f"/api/v1/files/{exp_job.id}/download")
    assert expired_res.status_code == 410


@pytest.mark.asyncio
async def test_convert_route_alias(client: AsyncClient):
    """Verify that both /convert and /convert-file create jobs properly."""
    response = await client.post(
        "/api/v1/convert",
        data={"to": "pdf", "input_key": "uploads/doc.txt", "from": "txt"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_create_video_job_with_url(client: AsyncClient):
    headers = _auth_headers()
    response = await client.post(
        "/api/v1/video/jobs",
        headers=headers,
        json={
            "operation": "url_download",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "params": {"format": "mp3"},
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
