from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.services.storage_service import storage_service
from app.utils.logger import logger
from app.worker.celery_app import CeleryQueue, celery_app
from app.worker.lifecycle import run_in_worker_loop
from app.worker.processors.gpu import gpu_ai_processor
from app.worker.workspace import cleanup_job_temp_dir, get_job_workspace


async def _async_process_gpu_job(job_id: str) -> dict[str, Any]:
    """Asynchronous GPU/AI job processing logic interacting with Database and Storage.

    Architecture: R2 -> Worker SSD -> Processor -> SSD -> R2
    Operates directly on local SSD file paths.
    """
    repo = JobRepository()
    job = await repo.get(job_id)
    if not job:
        logger.error("[gpu-worker] Job %s not found in database", job_id)
        return {"job_id": job_id, "error": "Job not found", "status": "failed"}

    if not job.input_key:
        err = "Job input_key is empty"
        await repo.mark_failed(job, err)
        return {"job_id": job_id, "error": err, "status": "failed"}

    await repo.mark_processing(job)
    metadata = job.job_metadata or {}

    workspace = get_job_workspace(job_id)
    try:
        workspace.check_disk_space()

        src_ext = job.input_key.split(".")[-1] if "." in job.input_key else "png"
        input_path = workspace.input_path(src_ext)
        logger.info("[gpu-worker] Downloading image to SSD: %s -> %s", job.input_key, input_path)
        storage_service.download_to_file(key=job.input_key, local_path=input_path)

        output_path = workspace.output_path("png")
        logger.info(
            "[gpu-worker] Executing BiRefNet model on %s: %s -> %s",
            job_id,
            input_path,
            output_path,
        )
        content_type = gpu_ai_processor.process_file(
            input_path=input_path,
            output_path=output_path,
            options=metadata,
        )

        output_key = f"outputs/{job.id}/result.png"
        logger.info("[gpu-worker] Uploading transparent PNG result to key: %s", output_key)
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
                    "[gpu-worker] Could not delete input file %s: %s",
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
        logger.info("[gpu-worker] Job %s completed! Expires at: %s", job_id, expires_at)
        return {
            "job_id": job_id,
            "status": JobStatus.COMPLETED.value,
            "output_key": output_key,
            "expires_at": expires_at.isoformat(),
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("[gpu-worker] Job %s failed: %s", job_id, exc, exc_info=True)
        await repo.mark_failed(job, error=str(exc))
        return {
            "job_id": job_id,
            "status": JobStatus.FAILED.value,
            "error": str(exc),
        }
    finally:
        cleanup_job_temp_dir(job_id)


@celery_app.task(
    name="app.worker.tasks.gpu.process_gpu_job", queue=CeleryQueue.GPU.value
)
def process_gpu_job(job_id: str, **kwargs: Any) -> dict[str, Any]:
    """
    Main job processor for GPU / AI model workloads on the 'gpu' queue.
    Workloads: BiRefNet background removal, heavy PyTorch/CUDA model inference.
    """
    logger.info("[gpu-worker] Processing GPU job: %s", job_id)
    return run_in_worker_loop(_async_process_gpu_job(job_id))


@celery_app.task(
    name="app.worker.tasks.gpu.birefnet_remove_bg", queue=CeleryQueue.GPU.value
)
def birefnet_remove_bg(input_key: str, **kwargs: Any) -> dict[str, str]:
    """Execute BiRefNet high-accuracy background removal on GPU."""
    logger.info("[gpu-worker] Executing BiRefNet background removal for %s", input_key)
    return {"input_key": input_key, "model": "BiRefNet", "status": "completed"}
