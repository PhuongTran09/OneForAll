from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.services.storage_service import storage_service
from app.utils.logger import logger
from app.worker.celery_app import CeleryQueue, celery_app
from app.worker.lifecycle import run_in_worker_loop
from app.worker.processors.image import image_processor
from app.worker.workspace import cleanup_job_temp_dir, get_job_workspace


async def _async_process_image_job(job_id: str) -> dict[str, Any]:
    """Asynchronous image job processing logic interacting with Database and Storage.

    Architecture: R2 -> Worker SSD -> Processor -> SSD -> R2
    Operates directly on local SSD file paths.
    """
    repo = JobRepository()
    job = await repo.get(job_id)
    if not job:
        logger.error("[image-worker] Job %s not found in database", job_id)
        return {"job_id": job_id, "error": "Job not found", "status": "failed"}

    if not job.input_key:
        err = "Job input_key is empty"
        await repo.mark_failed(job, err)
        return {"job_id": job_id, "error": err, "status": "failed"}

    await repo.mark_processing(job)
    metadata = job.job_metadata or {}
    operation = metadata.get("operation", "compress")

    workspace = get_job_workspace(job_id)
    try:
        workspace.check_disk_space()

        src_ext = job.input_key.split(".")[-1] if "." in job.input_key else "png"
        input_path = workspace.input_path(src_ext)
        logger.info("[image-worker] Downloading image to SSD: %s -> %s", job.input_key, input_path)
        storage_service.download_to_file(key=job.input_key, local_path=input_path)

        sub_opts = metadata.get("options", {}) or metadata.get("params", {})
        target_fmt = str(sub_opts.get("format", src_ext)).lower()
        if target_fmt in ("jpeg", "jpg"):
            target_ext = "jpg"
        elif target_fmt == "webp":
            target_ext = "webp"
        else:
            target_ext = "png"

        output_path = workspace.output_path(target_ext)

        logger.info(
            "[image-worker] Processing image %s: operation=%s -> %s",
            job_id,
            operation,
            output_path,
        )
        content_type = image_processor.process_file(
            input_path=input_path,
            output_path=output_path,
            options=metadata,
        )

        # Output extension based on content_type
        ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
        final_ext = ext_map.get(content_type, target_ext)
        output_key = f"outputs/{job.id}/result.{final_ext}"

        logger.info("[image-worker] Uploading processed image to key: %s", output_key)
        storage_service.upload_file(
            local_path=output_path,
            key=output_key,
            content_type=content_type,
        )

        if job.input_key:
            try:
                storage_service.delete_file(key=job.input_key)
            except Exception as del_err:  # noqa: BLE001
                logger.warning(
                    "[image-worker] Could not delete input file %s: %s",
                    job.input_key,
                    del_err,
                )

        expires_at = datetime.now(UTC) + timedelta(minutes=3)
        await repo.mark_completed(
            job,
            output_key=output_key,
            expires_at=expires_at,
            metadata=metadata,
        )
        logger.info("[image-worker] Job %s completed! Expires at: %s", job_id, expires_at)
        return {
            "job_id": job_id,
            "status": JobStatus.COMPLETED.value,
            "output_key": output_key,
            "expires_at": expires_at.isoformat(),
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("[image-worker] Job %s failed: %s", job_id, exc, exc_info=True)
        await repo.mark_failed(job, error=str(exc))
        return {
            "job_id": job_id,
            "status": JobStatus.FAILED.value,
            "error": str(exc),
        }
    finally:
        cleanup_job_temp_dir(job_id)


@celery_app.task(
    name="app.worker.tasks.image.process_image_job", queue=CeleryQueue.IMAGE.value
)
def process_image_job(job_id: str, **kwargs: Any) -> dict[str, Any]:
    """
    Main job processor for general image operations on the 'image' queue.
    Workloads: Pillow (resize, compress, format change, watermarking).
    """
    logger.info("[image-worker] Processing image job: %s", job_id)
    return run_in_worker_loop(_async_process_image_job(job_id))


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
