import io
from unittest.mock import patch

import pytest
from PIL import Image

from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.services.storage_service import storage_service
from app.worker.processors.document import document_processor
from app.worker.processors.video import video_audio_processor
from app.worker.tasks.gpu import process_gpu_job
from app.worker.tasks.image import process_image_job
from app.worker.tasks.video import process_video_job


def _create_sample_png() -> bytes:
    img = Image.new("RGB", (64, 64), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_process_image_job_resize_and_compress():
    png_bytes = _create_sample_png()
    input_key = "uploads/test_user/input_image.png"
    storage_service.upload_bytes(data=png_bytes, key=input_key, content_type="image/png")

    repo = JobRepository()
    job = await repo.create(
        user_id="test_user",
        type="image_process",
        input_key=input_key,
        metadata={
            "operation": "resize",
            "options": {"width": 32, "height": 32, "format": "JPEG", "quality": 80},
        },
    )

    result = process_image_job(job.id)
    assert result["status"] == JobStatus.COMPLETED.value
    assert result["output_key"] == f"outputs/{job.id}/result.jpg"

    updated = await repo.get(job.id)
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED.value
    assert updated.progress == 100


@pytest.mark.asyncio
async def test_process_video_job_url_download():
    repo = JobRepository()
    job = await repo.create(
        user_id="test_user",
        type="video",
        input_key=None,
        metadata={
            "operation": "url_download",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "options": {"format": "mp3"},
        },
    )

    fake_audio_bytes = b"ID3FakeMp3AudioData"

    with patch.object(
        video_audio_processor, "download_url", return_value=(fake_audio_bytes, "audio/mp3")
    ):
        result = process_video_job(job.id)

    assert result["status"] == JobStatus.COMPLETED.value
    assert result["output_key"] == f"outputs/{job.id}/result.mp3"

    updated = await repo.get(job.id)
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_process_video_job_tiktok_to_mp3():
    repo = JobRepository()
    job = await repo.create(
        user_id="test_user",
        type="video",
        input_key=None,
        metadata={
            "operation": "url_download",
            "url": "https://www.tiktok.com/@scout2015/video/6718335390845095173",
            "options": {"format": "mp3"},
        },
    )

    fake_mp3 = b"ID3FakeTikTokAudio"
    with patch.object(
        video_audio_processor, "download_url", return_value=(fake_mp3, "audio/mp3")
    ):
        result = process_video_job(job.id)

    assert result["status"] == JobStatus.COMPLETED.value
    assert result["output_key"] == f"outputs/{job.id}/result.mp3"

    updated = await repo.get(job.id)
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_process_video_job_tiktok_to_mp4():
    repo = JobRepository()
    job = await repo.create(
        user_id="test_user",
        type="video",
        input_key=None,
        metadata={
            "operation": "url_download",
            "url": "https://www.tiktok.com/@scout2015/video/6718335390845095173",
            "options": {"format": "mp4"},
        },
    )

    fake_mp4 = b"\x00\x00\x00\x1cftypisomFakeTikTokVideo"
    with patch.object(
        video_audio_processor, "download_url", return_value=(fake_mp4, "video/mp4")
    ):
        result = process_video_job(job.id)

    assert result["status"] == JobStatus.COMPLETED.value
    assert result["output_key"] == f"outputs/{job.id}/result.mp4"

    updated = await repo.get(job.id)
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_process_gpu_job_background_removal():
    png_bytes = _create_sample_png()
    input_key = "uploads/test_user/avatar.png"
    storage_service.upload_bytes(data=png_bytes, key=input_key, content_type="image/png")

    repo = JobRepository()
    job = await repo.create(
        user_id="test_user",
        type="gpu",
        input_key=input_key,
        metadata={"operation": "remove_background"},
    )

    fake_transparent_png = b"\x89PNG\r\n\x1a\nTransparentFakeData"
    with patch(
        "app.worker.processors.gpu.gpu_ai_processor.process",
        return_value=(fake_transparent_png, "image/png"),
    ):
        result = process_gpu_job(job.id)

    assert result["status"] == JobStatus.COMPLETED.value
    assert result["output_key"] == f"outputs/{job.id}/result.png"

    updated = await repo.get(job.id)
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED.value


def test_document_processor_xlsx_to_csv():
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Name", "Age"])
    ws.append(["Alice", 30])
    ws.append(["Bob", 25])

    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    csv_bytes, media_type = document_processor.process(
        xlsx_bytes,
        options={"operation": "xlsx-to-csv", "from": "xlsx", "to": "csv"},
    )
    assert "text/csv" in media_type
    assert b"Alice" in csv_bytes
    assert b"Bob" in csv_bytes
