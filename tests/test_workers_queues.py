import pytest

import app.worker as worker_pkg
import app.workers as workers_pkg
from app.services.task_queue_service import resolve_queue_and_task
from app.worker.celery_app import CeleryQueue, celery_app


def test_celery_app_queues_configured():
    queue_names = {q.name for q in celery_app.conf.task_queues}
    assert "convert" in queue_names
    assert "image" in queue_names
    assert "video" in queue_names
    assert "gpu" in queue_names


def test_cli_entrypoints():
    # Verify both app.workers and app.worker expose celery_app and app
    assert workers_pkg.celery_app is celery_app
    assert workers_pkg.app is celery_app
    assert worker_pkg.celery_app is celery_app
    assert worker_pkg.app is celery_app


def test_registered_tasks():
    registered = set(celery_app.tasks.keys())
    assert "app.worker.tasks.convert.process_convert_job" in registered
    assert "app.worker.tasks.image.process_image_job" in registered
    assert "app.worker.tasks.video.process_video_job" in registered
    assert "app.worker.tasks.gpu.process_gpu_job" in registered
    assert "app.worker.tasks.process_job" in registered


@pytest.mark.parametrize(
    ("job_type", "metadata", "expected_queue", "expected_task"),
    [
        # GPU (BiRefNet, AI model)
        (
            "image_process",
            {"operation": "remove_background"},
            CeleryQueue.GPU.value,
            "app.worker.tasks.gpu.process_gpu_job",
        ),
        (
            "gpu",
            {"operation": "birefnet"},
            CeleryQueue.GPU.value,
            "app.worker.tasks.gpu.process_gpu_job",
        ),
        # Convert (LibreOffice, VTracer)
        (
            "convert_file",
            {"operation": "docx-to-pdf"},
            CeleryQueue.CONVERT.value,
            "app.worker.tasks.convert.process_convert_job",
        ),
        (
            "convert",
            {"operation": "png-to-svg"},
            CeleryQueue.CONVERT.value,
            "app.worker.tasks.convert.process_convert_job",
        ),
        (
            "convert_file",
            {"operation": "vtracer"},
            CeleryQueue.CONVERT.value,
            "app.worker.tasks.convert.process_convert_job",
        ),
        # Image (Pillow)
        (
            "image_process",
            {"operation": "resize"},
            CeleryQueue.IMAGE.value,
            "app.worker.tasks.image.process_image_job",
        ),
        (
            "image",
            {"operation": "compress"},
            CeleryQueue.IMAGE.value,
            "app.worker.tasks.image.process_image_job",
        ),
        # Video (FFmpeg, yt-dlp)
        (
            "video",
            {"operation": "transcode"},
            CeleryQueue.VIDEO.value,
            "app.worker.tasks.video.process_video_job",
        ),
        (
            "video",
            {"operation": "extract-audio"},
            CeleryQueue.VIDEO.value,
            "app.worker.tasks.video.process_video_job",
        ),
        (
            "video",
            {"operation": "download"},
            CeleryQueue.VIDEO.value,
            "app.worker.tasks.video.process_video_job",
        ),
    ],
)
def test_resolve_queue_and_task(job_type, metadata, expected_queue, expected_task):
    queue, task = resolve_queue_and_task(job_type, metadata)
    assert queue == expected_queue
    assert task == expected_task
