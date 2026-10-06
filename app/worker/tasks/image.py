from typing import Any

from app.utils.logger import logger
from app.worker.celery_app import CeleryQueue, celery_app


@celery_app.task(
    name="app.worker.tasks.image.process_image_job", queue=CeleryQueue.IMAGE.value
)
def process_image_job(job_id: str, **kwargs: Any) -> dict[str, str]:
    """
    Main job processor for general image operations on the 'image' queue.
    Workloads: Pillow (resize, compress, format change, watermarking).
    """
    logger.info("[image-worker] Processing image job: %s", job_id)
    return {"job_id": job_id, "queue": CeleryQueue.IMAGE.value, "status": "processing"}


@celery_app.task(
    name="app.worker.tasks.image.pillow_process", queue=CeleryQueue.IMAGE.value
)
def pillow_process(
    input_key: str, operation: str, options: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Execute standard Pillow image processing operation."""
    logger.info(
        "[image-worker] Executing Pillow operation %s for %s", operation, input_key
    )
    return {"input_key": input_key, "operation": operation, "status": "completed"}
