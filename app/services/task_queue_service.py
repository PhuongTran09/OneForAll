from typing import Any

from app.core.config import settings
from app.utils.logger import logger
from app.worker.celery_app import CeleryQueue


def resolve_queue_and_task(
    job_type: str, metadata: dict[str, Any] | None = None
) -> tuple[str, str]:
    """
    Resolve target Celery queue and task based on job_type and operation metadata:
    - convert: LibreOffice, VTracer, document conversion (PDF, DOCX, XLSX, SVG)
    - image: Pillow (resize, compress, format convert)
    - video: FFmpeg (transcode, extract-audio, thumbnail), yt-dlp
    - gpu: BiRefNet background removal, AI model inference
    """
    meta = metadata or {}
    op = str(meta.get("operation", "")).lower()

    # 1. GPU Queue: AI models requiring VRAM / CUDA
    if job_type in ("gpu", "bg_removal") or op in ("remove_background", "birefnet"):
        return (CeleryQueue.GPU.value, "app.worker.tasks.gpu.process_gpu_job")

    # 2. Video Queue: FFmpeg, yt-dlp
    if job_type in ("video", "video_process") or op in (
        "transcode",
        "extract-audio",
        "thumbnail",
        "ytdlp",
        "download",
    ):
        return (CeleryQueue.VIDEO.value, "app.worker.tasks.video.process_video_job")

    # 3. Convert Queue: LibreOffice, VTracer, document conversions
    if (
        job_type in ("convert", "convert_file")
        or "-to-" in op
        or "_to_" in op
        or op in ("vtracer", "libreoffice")
    ):
        return (
            CeleryQueue.CONVERT.value,
            "app.worker.tasks.convert.process_convert_job",
        )

    # 4. Image Queue: Pillow (resize, compress, etc.)
    if job_type in ("image", "image_process") or op in (
        "compress",
        "resize",
        "crop",
        "pillow",
    ):
        return (CeleryQueue.IMAGE.value, "app.worker.tasks.image.process_image_job")

    # Fallback to configured default queue
    default_q = getattr(settings, "CELERY_DEFAULT_QUEUE", CeleryQueue.CONVERT.value)
    default_t = getattr(
        settings, "CELERY_PROCESS_JOB_TASK", "app.worker.tasks.process_job"
    )
    return (default_q, default_t)


class TaskQueueService:
    def enqueue_job(
        self,
        *,
        job_id: str,
        job_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        queue: str | None = None,
        task_name: str | None = None,
    ) -> str | None:
        """
        Enqueues a job into Celery with dedicated queue routing.
        """
        try:
            from app.worker.celery_app import celery_app
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Celery is not available; job %s remains queued: %s", job_id, exc
            )
            return None

        resolved_q, resolved_task = resolve_queue_and_task(job_type or "", metadata)
        target_queue = queue or resolved_q
        target_task = task_name or resolved_task

        try:
            result = celery_app.send_task(
                target_task,
                kwargs={"job_id": job_id},
                queue=target_queue,
            )
            logger.info(
                "Enqueued job %s -> task=%s, queue=%s, task_id=%s",
                job_id,
                target_task,
                target_queue,
                result.id,
            )
            return result.id
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to enqueue job %s to queue %s: %s", job_id, target_queue, exc
            )
            return None


task_queue_service = TaskQueueService()
