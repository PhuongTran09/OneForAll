from typing import Any

from app.worker.celery_app import celery_app
from app.worker.tasks.cleanup import cleanup_expired_jobs_task
from app.worker.tasks.convert import (
    libreoffice_convert,
    process_convert_job,
    vtracer_convert,
)
from app.worker.tasks.gpu import birefnet_remove_bg, process_gpu_job
from app.worker.tasks.image import pillow_process, process_image_job
from app.worker.tasks.video import ffmpeg_process, process_video_job, ytdlp_download


@celery_app.task(name="app.worker.tasks.process_job")
def process_job(job_id: str, **kwargs: Any) -> dict[str, str]:
    """
    Backward-compatible generic job processor.
    Routes to PostgreSQL status updates or delegates to specific workers.
    """
    return {"job_id": job_id, "status": "queued"}


__all__ = [
    "birefnet_remove_bg",
    "cleanup_expired_jobs_task",
    "ffmpeg_process",
    "libreoffice_convert",
    "pillow_process",
    "process_convert_job",
    "process_gpu_job",
    "process_image_job",
    "process_job",
    "process_video_job",
    "vtracer_convert",
    "ytdlp_download",
]
