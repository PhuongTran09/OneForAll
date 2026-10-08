from datetime import UTC, datetime
from typing import Any

from app.repositories.job_repository import JobRepository
from app.services.storage_service import storage_service
from app.utils.logger import logger
from app.worker.celery_app import celery_app
from app.worker.lifecycle import run_in_worker_loop


async def _async_cleanup_expired_jobs() -> dict[str, Any]:
    """
    Quét Database và xóa các file kết quả đã quá hạn expires_at (20 phút).
    Cập nhật status sang 'expired'.
    """
    now = datetime.now(UTC)
    cleaned_count = 0

    repo = JobRepository()
    expired_jobs = await repo.get_expired_jobs(now)

    for job in expired_jobs:
        logger.info(
            "[cleanup-worker] Processing expired job: %s (expires_at: %s)",
            job.id,
            job.expires_at,
        )

        # 1. Xóa file output trên R2
        if job.output_key:
            try:
                storage_service.delete_file(key=job.output_key)
                logger.info(
                    "[cleanup-worker] Deleted expired output file: %s",
                    job.output_key,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[cleanup-worker] Failed to delete output file %s: %s",
                    job.output_key,
                    exc,
                )

        # 2. Xóa file input nếu còn sót lại
        if job.input_key:
            try:
                storage_service.delete_file(key=job.input_key)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[cleanup-worker] Failed to delete input file %s: %s",
                    job.input_key,
                    exc,
                )

        # 3. DELETE job khỏi Database (idempotent)
        try:
            await repo.delete(job.id)
            logger.info("[cleanup-worker] Deleted expired job record: %s", job.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[cleanup-worker] Failed to delete job record %s: %s", job.id, exc)
        cleaned_count += 1

    logger.info(
        "[cleanup-worker] Cleanup finished. Total expired jobs cleaned: %d",
        cleaned_count,
    )
    return {"cleaned_count": cleaned_count, "timestamp": now.isoformat()}


@celery_app.task(name="app.worker.tasks.cleanup.cleanup_expired_jobs_task")
def cleanup_expired_jobs_task() -> dict[str, Any]:
    """
    Periodic task chạy định kỳ mỗi 1 phút để dọn dẹp file hết hạn.
    """
    logger.info("[cleanup-worker] Starting periodic cleanup job check...")
    return run_in_worker_loop(_async_cleanup_expired_jobs())
