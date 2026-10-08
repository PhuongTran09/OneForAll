import io
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.services.storage_service import storage_service
from app.worker.tasks.cleanup import cleanup_expired_jobs_task
from app.worker.tasks.convert import process_convert_job


@pytest.mark.asyncio
async def test_process_convert_job_png_to_svg():
    # 1. Create a dummy PNG in storage
    img = Image.new("RGB", (32, 32), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    input_key = "uploads/test_user/test_icon.png"
    storage_service.upload_bytes(
        data=png_bytes, key=input_key, content_type="image/png"
    )

    # 2. Insert Job in Supabase database
    repo = JobRepository()
    job = await repo.create(
        user_id="test_user",
        type="convert_file",
        input_key=input_key,
        metadata={
            "from": "png",
            "to": "svg",
            "operation": "png-to-svg",
            "options": {"colormode": "color", "mode": "spline"},
        },
    )
    job_id = job.id

    # 3. Execute Worker task directly
    result = process_convert_job(job_id)
    assert result["status"] == "completed"
    assert "output_key" in result
    assert result["output_key"] == f"outputs/{job_id}/result.svg"
    assert "expires_at" in result

    # 4. Verify DB was updated
    updated_job = await repo.get(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.COMPLETED.value
    assert updated_job.progress == 100
    assert updated_job.output_key == result["output_key"]
    assert updated_job.expires_at is not None


@pytest.mark.asyncio
async def test_cleanup_expired_jobs():
    from tests.conftest import _fake_storage

    # 1. Create a completed job that expired 5 minutes ago with both input and output files
    input_key = "uploads/expired_job/original.png"
    output_key = "outputs/expired_job/result.svg"
    storage_service.upload_bytes(
        data=b"original", key=input_key, content_type="image/png"
    )
    storage_service.upload_bytes(
        data=b"<svg></svg>", key=output_key, content_type="image/svg+xml"
    )
    assert input_key in _fake_storage
    assert output_key in _fake_storage

    repo = JobRepository()
    job = await repo.create(
        user_id="test_user",
        type="convert_file",
        input_key=input_key,
        metadata={},
    )
    job_id = job.id
    expired_time = datetime.now(UTC) - timedelta(minutes=5)
    await repo.mark_completed(job, output_key=output_key, expires_at=expired_time)

    # 2. Run cleanup task (delete output, delete input, status=expired)
    cleanup_result = cleanup_expired_jobs_task()
    assert cleanup_result["cleaned_count"] >= 1
    assert input_key not in _fake_storage
    assert output_key not in _fake_storage

    # 3. Verify Job is deleted from DB upon expiry
    cleaned_job = await repo.get(job_id)
    assert cleaned_job is None

    # 4. Run cleanup again when no expired jobs exist (No -> 0)
    no_jobs_result = cleanup_expired_jobs_task()
    assert no_jobs_result["cleaned_count"] == 0


@pytest.mark.asyncio
async def test_process_convert_job_consecutive_runs():
    """Verify multiple consecutive task executions do NOT raise 'Event loop is closed'."""
    from app.worker.lifecycle import get_worker_loop_manager

    manager = get_worker_loop_manager()
    loop_before = manager.loop

    for i in range(3):
        img = Image.new("RGB", (16, 16), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        input_key = f"uploads/test_user/test_run_{i}.png"
        storage_service.upload_bytes(
            data=png_bytes, key=input_key, content_type="image/png"
        )

        repo = JobRepository()
        job = await repo.create(
            user_id="test_user",
            type="convert_file",
            input_key=input_key,
            metadata={
                "from": "png",
                "to": "svg",
                "operation": "png-to-svg",
                "options": {"colormode": "color", "mode": "spline"},
            },
        )

        result = process_convert_job(job.id)
        assert result["status"] == "completed"

    loop_after = manager.loop
    assert loop_after is not None
    assert not loop_after.is_closed()
    if loop_before is not None:
        assert loop_before is loop_after

