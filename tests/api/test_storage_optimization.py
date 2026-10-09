import io
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.services.storage_service import storage_service
from tests.conftest import _fake_storage


@pytest.mark.asyncio
async def test_successful_direct_download_deletes_r2_and_job(client: AsyncClient):
    """Khi user tải stream/direct thành công: xóa output R2 ngay và DELETE job khỏi DB."""
    repo = JobRepository()
    job = await repo.create(
        user_id="anonymous",
        type="convert",
        input_key=None,
    )
    output_key = f"outputs/{job.id}/result.mp3"
    storage_service.upload_bytes(data=b"ID3FakeMp3Content12345678", key=output_key, content_type="audio/mp3")
    await repo.mark_completed(
        job,
        output_key=output_key,
        expires_at=datetime.now(UTC) + timedelta(minutes=3),
    )

    assert output_key in _fake_storage
    assert await repo.get(job.id) is not None

    # Tải qua direct binary stream
    resp = await client.get(f"/api/v1/files/{job.id}/download?direct=true")
    assert resp.status_code == 200
    assert resp.content == b"ID3FakeMp3Content12345678"

    # Sau khi download stream thành công: R2 output và Job DB phải bị xóa ngay lập tức
    assert output_key not in _fake_storage
    assert await repo.get(job.id) is None


@pytest.mark.asyncio
async def test_aborted_download_stream_keeps_file_for_retry(client: AsyncClient):
    """Nếu download stream bị lỗi hoặc disconnect giữa chừng: không xóa file R2 và giữ job để user retry."""
    repo = JobRepository()
    job = await repo.create(
        user_id="anonymous",
        type="convert",
        input_key=None,
    )
    output_key = f"outputs/{job.id}/result.mp3"
    storage_service.upload_bytes(data=b"chunk1_chunk2_chunk3", key=output_key, content_type="audio/mp3")
    await repo.mark_completed(
        job,
        output_key=output_key,
        expires_at=datetime.now(UTC) + timedelta(minutes=3),
    )

    def failing_stream(key: str):
        yield b"chunk1_"
        raise ConnectionResetError("Client disconnected unexpectedly")

    with patch.object(storage_service, "download_stream", side_effect=failing_stream):
        with pytest.raises(ConnectionResetError):
            await client.get(f"/api/v1/files/{job.id}/download?direct=true")

    # File R2 và Job DB vẫn phải còn nguyên để user có thể retry
    assert output_key in _fake_storage
    assert await repo.get(job.id) is not None


@pytest.mark.asyncio
async def test_consumed_endpoint_deletes_r2_and_job(client: AsyncClient):
    """Khi client thông báo đã tải xong qua presigned url (endpoint consumed): xóa R2 và DELETE job."""
    repo = JobRepository()
    job = await repo.create(
        user_id="anonymous",
        type="convert",
        input_key=None,
    )
    output_key = f"outputs/{job.id}/result.pdf"
    storage_service.upload_bytes(data=b"%PDF-1.4 Fake", key=output_key, content_type="application/pdf")
    await repo.mark_completed(
        job,
        output_key=output_key,
        expires_at=datetime.now(UTC) + timedelta(minutes=3),
    )

    # Gọi POST /files/{job_id}/consumed
    resp = await client.post(f"/api/v1/files/{job.id}/consumed")
    assert resp.status_code == 200

    # R2 và Job phải được xóa
    assert output_key not in _fake_storage
    assert await repo.get(job.id) is None


@pytest.mark.asyncio
async def test_expired_download_cleans_up_and_returns_410(client: AsyncClient):
    """Khi job quá hạn 3 phút mà chưa tải: xóa R2, DELETE job và trả về 410 Gone."""
    repo = JobRepository()
    job = await repo.create(
        user_id="anonymous",
        type="video",
        input_key=None,
    )
    output_key = f"outputs/{job.id}/result.mp4"
    storage_service.upload_bytes(data=b"fake-mp4", key=output_key, content_type="video/mp4")
    past_time = datetime.now(UTC) - timedelta(minutes=4)
    await repo.mark_completed(job, output_key=output_key, expires_at=past_time)

    resp = await client.get(f"/api/v1/files/{job.id}/download")
    assert resp.status_code == 410

    # R2 output và Job DB phải bị xóa
    assert output_key not in _fake_storage
    assert await repo.get(job.id) is None


@pytest.mark.asyncio
async def test_download_uses_custom_title_in_content_disposition(client: AsyncClient):
    """File download phải lấy đúng tiêu đề (title hoặc original_filename) thay vì result.mp4."""
    repo = JobRepository()
    job = await repo.create(
        user_id="anonymous",
        type="video",
        input_key=None,
        metadata={"title": "Rick Astley - Never Gonna Give You Up"},
    )
    output_key = f"outputs/{job.id}/result.mp4"
    storage_service.upload_bytes(data=b"fake-video-content", key=output_key, content_type="video/mp4")
    await repo.mark_completed(
        job,
        output_key=output_key,
        expires_at=datetime.now(UTC) + timedelta(minutes=3),
        metadata=job.job_metadata,
    )

    resp = await client.get(f"/api/v1/files/{job.id}/download?direct=true")
    assert resp.status_code == 200
    disposition = resp.headers.get("content-disposition", "")
    assert 'filename="Rick Astley - Never Gonna Give You Up.mp4"' in disposition
    assert "filename*=UTF-8''Rick%20Astley%20-%20Never%20Gonna%20Give%20You%20Up.mp4" in disposition


@pytest.mark.asyncio
async def test_download_uses_original_filename_fallback(client: AsyncClient):
    """File download fallback về original_filename nếu không có title từ URL."""
    repo = JobRepository()
    job = await repo.create(
        user_id="anonymous",
        type="convert",
        input_key=None,
        metadata={"original_filename": "BaoCaoTaiChinh2024.docx"},
    )
    output_key = f"outputs/{job.id}/result.pdf"
    storage_service.upload_bytes(data=b"%PDF-1.4 Fake", key=output_key, content_type="application/pdf")
    await repo.mark_completed(
        job,
        output_key=output_key,
        expires_at=datetime.now(UTC) + timedelta(minutes=3),
        metadata=job.job_metadata,
    )

    resp = await client.get(f"/api/v1/files/{job.id}/download?direct=true")
    assert resp.status_code == 200
    disposition = resp.headers.get("content-disposition", "")
    assert 'filename="BaoCaoTaiChinh2024.pdf"' in disposition

