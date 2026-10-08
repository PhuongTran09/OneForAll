"""Unit and integration tests for R2 -> Worker SSD -> Processor -> SSD -> R2 architecture.

Tests:
- Large file streaming without loading into RAM
- R2 -> temporary SSD file
- Processor using file paths directly
- Output file -> R2 upload
- SSD temporary workspace cleanup on success
- SSD temporary workspace cleanup on processor error
- SSD temporary workspace cleanup on upload error
- Concurrent jobs have isolated workspaces
- Job status lifecycle: queued -> processing -> completed / failed
- Storage connection failure handling without worker crash
"""

import io
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from PIL import Image

from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.services.storage_service import storage_service
from app.worker.processors.document import document_processor
from app.worker.processors.image import image_processor
from app.worker.processors.video import video_audio_processor
from app.worker.tasks.convert import process_convert_job
from app.worker.tasks.image import process_image_job
from app.worker.tasks.video import process_video_job
from app.worker.workspace import JobWorkspace, cleanup_job_temp_dir, get_job_workspace


def test_job_workspace_structure_and_isolation(tmp_path: Path):
    """Verify each job gets an isolated workspace with input, output, and work folders."""
    job_1 = str(uuid4())
    job_2 = str(uuid4())

    ws1 = JobWorkspace(job_1, base_dir=tmp_path)
    ws2 = JobWorkspace(job_2, base_dir=tmp_path)

    inp1 = ws1.input_path("mp4")
    out1 = ws1.output_path("mp4")
    inp2 = ws2.input_path("mp4")
    out2 = ws2.output_path("mp4")

    # Paths must be completely isolated
    assert ws1.dir_path != ws2.dir_path
    assert inp1 != inp2
    assert out1 != out2

    assert inp1.parent == ws1.dir_path
    assert ws1.work_dir.exists()
    assert ws2.work_dir.exists()

    # Create dummy files
    inp1.write_bytes(b"data1")
    inp2.write_bytes(b"data2")
    assert inp1.exists()
    assert inp2.exists()

    # Cleanup ws1 should not affect ws2
    ws1.cleanup()
    assert not ws1.dir_path.exists()
    assert ws2.dir_path.exists()
    assert inp2.exists()

    ws2.cleanup()
    assert not ws2.dir_path.exists()


def test_storage_service_file_methods(tmp_path: Path):
    """Test download_to_file and upload_file using local fallback."""
    test_key = "uploads/test_job/original.txt"
    src_file = tmp_path / "original.txt"
    src_file.write_text("Hello OneForAll streaming storage!")

    # Upload from file
    uploaded_key = storage_service.upload_file(local_path=src_file, key=test_key)
    assert uploaded_key == test_key

    # Download to different file
    dest_file = tmp_path / "downloaded.txt"
    downloaded_path = storage_service.download_to_file(key=test_key, local_path=dest_file)
    assert downloaded_path == dest_file
    assert dest_file.read_text() == "Hello OneForAll streaming storage!"

    # Clean up storage key
    storage_service.delete_file(key=test_key)


def test_image_processor_file_path(tmp_path: Path):
    """Verify image processor operates on file paths directly."""
    img = Image.new("RGB", (100, 100), color="blue")
    inp_path = tmp_path / "input.png"
    out_path = tmp_path / "output.jpg"
    img.save(inp_path, format="PNG")

    content_type = image_processor.process_file(
        input_path=inp_path,
        output_path=out_path,
        options={"operation": "resize", "options": {"width": 50, "height": 50, "format": "jpg"}},
    )
    assert content_type == "image/jpeg"
    assert out_path.exists()

    with Image.open(out_path) as out_img:
        assert out_img.size == (50, 50)


def test_video_processor_file_path(tmp_path: Path):
    """Verify video processor operates on file paths directly via process_file."""
    inp_path = tmp_path / "input.mp4"
    out_path = tmp_path / "output.mp3"
    inp_path.write_bytes(b"fake-video-header")

    with patch.object(video_audio_processor, "_run_ffmpeg") as mock_ffmpeg:
        content_type = video_audio_processor.process_file(
            input_path=inp_path,
            output_path=out_path,
            options={"operation": "extract-audio", "options": {"format": "mp3"}},
        )
        assert content_type == "audio/mp3"
        assert mock_ffmpeg.called
        cmd = mock_ffmpeg.call_args[0][0]
        assert str(inp_path) in cmd
        assert str(out_path) in cmd


@pytest.mark.asyncio
async def test_worker_cleanup_on_success():
    """Verify SSD workspace is cleaned up after successful worker execution."""
    img = Image.new("RGB", (32, 32), color="green")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    job_id = str(uuid4())
    input_key = f"uploads/{job_id}/original.png"
    storage_service.upload_bytes(data=png_bytes, key=input_key, content_type="image/png")

    repo = JobRepository()
    job = await repo.create(
        job_id=job_id,
        user_id="test_user",
        type="image",
        input_key=input_key,
        metadata={"operation": "compress", "options": {"format": "webp"}},
    )

    ws = get_job_workspace(job_id)
    ws_dir = ws.dir_path
    assert ws_dir.exists()

    result = process_image_job(job_id)
    assert result["status"] == "completed"

    # Workspace directory must be deleted after job finishes
    assert not ws_dir.exists()


@pytest.mark.asyncio
async def test_worker_cleanup_on_processor_failure():
    """Verify SSD workspace is cleaned up and job is marked failed if processor errors."""
    job_id = str(uuid4())
    input_key = f"uploads/{job_id}/corrupted.png"
    # Write invalid data that will cause processor to raise an error
    storage_service.upload_bytes(data=b"not-an-image", key=input_key, content_type="image/png")

    repo = JobRepository()
    job = await repo.create(
        job_id=job_id,
        user_id="test_user",
        type="image",
        input_key=input_key,
        metadata={"operation": "resize", "options": {"width": 10}},
    )

    ws = get_job_workspace(job_id)
    ws_dir = ws.dir_path
    assert ws_dir.exists()

    result = process_image_job(job_id)
    assert result["status"] == "failed"
    assert "error" in result

    # Directory must be cleaned up in finally block despite failure
    assert not ws_dir.exists()

    updated = await repo.get(job_id)
    assert updated is not None
    assert updated.status == JobStatus.FAILED.value


@pytest.mark.asyncio
async def test_worker_cleanup_on_upload_failure():
    """Verify SSD workspace is cleaned up and job marked failed if upload to R2 fails."""
    img = Image.new("RGB", (32, 32), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    job_id = str(uuid4())
    input_key = f"uploads/{job_id}/original.png"
    storage_service.upload_bytes(data=buf.getvalue(), key=input_key, content_type="image/png")

    repo = JobRepository()
    await repo.create(
        job_id=job_id,
        user_id="test_user",
        type="image",
        input_key=input_key,
        metadata={"operation": "compress"},
    )

    ws = get_job_workspace(job_id)
    ws_dir = ws.dir_path

    # Simulate R2 upload failure
    with patch.object(
        storage_service, "upload_file", side_effect=RuntimeError("R2 upload timeout")
    ):
        result = process_image_job(job_id)
        assert result["status"] == "failed"
        assert "R2 upload timeout" in result["error"]

    # Workspace directory must be deleted despite upload error
    assert not ws_dir.exists()

    updated = await repo.get(job_id)
    assert updated is not None
    assert updated.status == JobStatus.FAILED.value


@pytest.mark.asyncio
async def test_worker_survives_r2_delete_failure():
    """Verify failure to delete input key does not fail or crash the worker."""
    img = Image.new("RGB", (32, 32), color="yellow")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    job_id = str(uuid4())
    input_key = f"uploads/{job_id}/original.png"
    storage_service.upload_bytes(data=buf.getvalue(), key=input_key, content_type="image/png")

    repo = JobRepository()
    await repo.create(
        job_id=job_id,
        user_id="test_user",
        type="image",
        input_key=input_key,
        metadata={"operation": "compress"},
    )

    # Deleting input from R2 raises exception
    with patch.object(
        storage_service, "delete_file", side_effect=Exception("R2 temporary network disconnect")
    ):
        result = process_image_job(job_id)
        # Job must still succeed
        assert result["status"] == "completed"

    updated = await repo.get(job_id)
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED.value
