from typing import Any

from app.utils.logger import logger
from app.worker.celery_app import CeleryQueue, celery_app


@celery_app.task(
    name="app.worker.tasks.video.process_video_job", queue=CeleryQueue.VIDEO.value
)
def process_video_job(job_id: str, **kwargs: Any) -> dict[str, str]:
    """
    Main job processor for video processing on the 'video' queue.
    Workloads: FFmpeg (transcoding, audio extraction, thumbnailing) & yt-dlp.
    """
    logger.info("[video-worker] Processing video job: %s", job_id)
    return {"job_id": job_id, "queue": CeleryQueue.VIDEO.value, "status": "processing"}


@celery_app.task(
    name="app.worker.tasks.video.ffmpeg_process", queue=CeleryQueue.VIDEO.value
)
def ffmpeg_process(
    input_key: str, operation: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Execute FFmpeg command (e.g. transcode, extract-audio, thumbnail generation)."""
    logger.info("[video-worker] Executing FFmpeg %s on %s", operation, input_key)
    return {"input_key": input_key, "operation": operation, "status": "completed"}


@celery_app.task(
    name="app.worker.tasks.video.ytdlp_download", queue=CeleryQueue.VIDEO.value
)
def ytdlp_download(url: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute yt-dlp video downloading or audio extraction."""
    logger.info("[video-worker] Executing yt-dlp for %s", url)
    return {"url": url, "status": "completed"}
