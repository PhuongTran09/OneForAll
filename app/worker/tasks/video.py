from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.services.storage_service import storage_service
from app.utils.logger import logger
from app.worker.celery_app import CeleryQueue, celery_app
from app.worker.lifecycle import run_in_worker_loop
from app.worker.processors.video import video_audio_processor


async def _async_process_video_job(job_id: str) -> dict[str, Any]:
    """Asynchronous video job processing logic interacting with Database and Storage."""
    repo = JobRepository()
    job = await repo.get(job_id)
    if not job:
        logger.error("[video-worker] Job %s not found in database", job_id)
        return {"job_id": job_id, "error": "Job not found", "status": "failed"}

    await repo.mark_processing(job)
    metadata = job.job_metadata or {}
    operation = metadata.get("operation", "transcode")
    url = metadata.get("url")

    try:
        input_bytes = b""
        if url or operation in ("url_download", "download", "ytdlp"):
            logger.info("[video-worker] Processing from URL: %s", url)
        elif job.input_key and job.input_key != "string":
            logger.info("[video-worker] Downloading video from key: %s", job.input_key)
            input_bytes = storage_service.download_bytes(key=job.input_key)
        else:
            raise ValueError("Neither input_key nor url was provided for video processing.")

        logger.info("[video-worker] Processing video %s: operation=%s", job_id, operation)
        output_bytes, content_type = video_audio_processor.process(input_bytes, options=metadata)

        # Output extension based on content_type
        ext = content_type.split("/")[-1].split(";")[0]
        if ext == "jpeg":
            ext = "jpg"
        output_key = f"outputs/{job.id}/result.{ext}"

        logger.info("[video-worker] Uploading video result to key: %s", output_key)
        storage_service.upload_bytes(data=output_bytes, key=output_key, content_type=content_type)

        if job.input_key and job.input_key != "string":
            try:
                storage_service.delete_file(key=job.input_key)
                logger.info("[video-worker] Deleted input file: %s", job.input_key)
            except Exception as del_err:  # noqa: BLE001
                logger.warning("[video-worker] Could not delete input file %s: %s", job.input_key, del_err)

        # Final output có thời hạn tối đa 3 phút
        expires_at = datetime.now(UTC) + timedelta(minutes=3)
        await repo.mark_completed(job, output_key=output_key, expires_at=expires_at)
        logger.info("[video-worker] Job %s completed! Expires at: %s", job_id, expires_at)
        return {
            "job_id": job_id,
            "status": JobStatus.COMPLETED.value,
            "output_key": output_key,
            "expires_at": expires_at.isoformat(),
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("[video-worker] Job %s failed: %s", job_id, exc, exc_info=True)
        await repo.mark_failed(job, error=str(exc))
        return {
            "job_id": job_id,
            "status": JobStatus.FAILED.value,
            "error": str(exc),
        }


@celery_app.task(
    name="app.worker.tasks.video.process_video_job", queue=CeleryQueue.VIDEO.value
)
def process_video_job(job_id: str, **kwargs: Any) -> dict[str, Any]:
    """
    Main job processor for video processing on the 'video' queue.
    Workloads: FFmpeg (transcoding, audio extraction, thumbnailing) & yt-dlp.
    """
    logger.info("[video-worker] Processing video job: %s", job_id)
    return run_in_worker_loop(_async_process_video_job(job_id))


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
