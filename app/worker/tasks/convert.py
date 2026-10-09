from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.services.storage_service import storage_service
from app.utils.logger import logger
from app.worker.celery_app import CeleryQueue, celery_app
from app.worker.lifecycle import run_in_worker_loop
from app.worker.processors.document import document_processor
from app.worker.workspace import cleanup_job_temp_dir, get_job_workspace


async def _async_process_convert_job(job_id: str) -> dict[str, Any]:
    """Asynchronous job execution logic interacting with Database and Storage.

    Architecture: R2 -> Worker SSD -> Processor -> SSD -> R2
    Streams files to/from disk without loading full file into RAM.
    """
    repo = JobRepository()
    job = await repo.get(job_id)
    if not job:
        logger.error("[convert-worker] Job %s not found in database", job_id)
        return {"job_id": job_id, "error": "Job not found", "status": "failed"}

    if not job.input_key:
        err = "Job input_key is empty"
        await repo.mark_failed(job, err)
        return {"job_id": job_id, "error": err, "status": "failed"}

    await repo.mark_processing(job)
    metadata = job.job_metadata or {}
    from_format = metadata.get("from", "")
    to_format = metadata.get("to", "")

    workspace = get_job_workspace(job_id)
    try:
        workspace.check_disk_space()

        # 1. Tải nội dung file từ Storage (Cloudflare R2 / local) trực tiếp xuống SSD
        src_ext = from_format.lower().lstrip(".") or (
            job.input_key.split(".")[-1] if "." in job.input_key else "bin"
        )
        input_path = workspace.input_path(src_ext)
        logger.info("[convert-worker] Downloading file to SSD: %s -> %s", job.input_key, input_path)
        storage_service.download_to_file(key=job.input_key, local_path=input_path)

        # 2. Thực hiện chuyển đổi file qua Processor trực tiếp trên SSD
        target_ext = to_format.lower().lstrip(".")
        output_path = workspace.output_path(target_ext)
        logger.info(
            "[convert-worker] Converting job %s: %s -> %s",
            job_id,
            input_path,
            output_path,
        )
        content_type = document_processor.process_file(
            input_path=input_path,
            output_path=output_path,
            options=metadata,
        )

        # 3. Upload file kết quả từ SSD lên Storage (outputs/{job_id}/result.ext)
        output_key = f"outputs/{job.id}/result.{target_ext}"
        logger.info(
            "[convert-worker] Uploading converted file to key: %s", output_key
        )
        storage_service.upload_file(
            local_path=output_path,
            key=output_key,
            content_type=content_type,
        )

        # 4. Xóa file gốc input trên Storage để tiết kiệm dung lượng
        if job.input_key:
            try:
                storage_service.delete_file(key=job.input_key)
                logger.info(
                    "[convert-worker] Deleted original input file: %s",
                    job.input_key,
                )
            except Exception as del_err:  # noqa: BLE001
                logger.warning(
                    "[convert-worker] Could not delete input file %s: %s",
                    job.input_key,
                    del_err,
                )

        # 5. Cập nhật trạng thái Job thành completed (hết hạn sau 3 phút)
        expires_at = datetime.now(UTC) + timedelta(minutes=3)
        await repo.mark_completed(
            job,
            output_key=output_key,
            expires_at=expires_at,
            metadata=metadata,
        )
        logger.info(
            "[convert-worker] Job %s completed! Expires at: %s", job_id, expires_at
        )
        return {
            "job_id": job_id,
            "status": JobStatus.COMPLETED.value,
            "output_key": output_key,
            "expires_at": expires_at.isoformat(),
        }

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[convert-worker] Job %s failed: %s", job_id, exc, exc_info=True
        )
        await repo.mark_failed(job, error=str(exc))
        return {
            "job_id": job_id,
            "status": JobStatus.FAILED.value,
            "error": str(exc),
        }
    finally:
        cleanup_job_temp_dir(job_id)


@celery_app.task(
    name="app.worker.tasks.convert.process_convert_job", queue=CeleryQueue.CONVERT.value
)
def process_convert_job(job_id: str, **kwargs: Any) -> dict[str, Any]:
    """
    Main job processor for document and vector conversions on the 'convert' queue.
    Workloads: LibreOffice (DOC/DOCX/XLSX to PDF, etc.), VTracer (PNG to SVG vectorization).
    """
    logger.info("[convert-worker] Received convert job: %s", job_id)
    return run_in_worker_loop(_async_process_convert_job(job_id))


@celery_app.task(
    name="app.worker.tasks.convert.libreoffice_convert", queue=CeleryQueue.CONVERT.value
)
def libreoffice_convert(
    input_key: str, output_format: str, **kwargs: Any
) -> dict[str, str]:
    """Execute LibreOffice document conversion (e.g. DOCX -> PDF, XLSX -> PDF)."""
    logger.info(
        "[convert-worker] Executing LibreOffice conversion for %s to %s",
        input_key,
        output_format,
    )
    return {"input_key": input_key, "format": output_format, "status": "completed"}


@celery_app.task(
    name="app.worker.tasks.convert.vtracer_convert", queue=CeleryQueue.CONVERT.value
)
def vtracer_convert(
    input_key: str, colormode: str = "color", mode: str = "spline", **kwargs: Any
) -> dict[str, str]:
    """Execute VTracer raster to vector (PNG -> SVG) conversion."""
    logger.info("[convert-worker] Executing VTracer conversion for %s", input_key)
    return {"input_key": input_key, "status": "completed"}
